from __future__ import annotations

import json
import math
import statistics
import time
import urllib.request
from datetime import datetime
from typing import Dict, List, Tuple

from .models import AssetKey, MarketAssetSnapshot, MarketSnapshot
from .rules import default_market_snapshot
from .strategies import ASSET_NAMES


EASTMONEY_SOURCES: Dict[AssetKey, Tuple[str, str]] = {
    "china_large": ("1.000300", "东方财富: 沪深300代理中证A500/A股大盘"),
    "china_mid": ("1.000905", "东方财富: 中证500"),
    "china_dividend": ("1.000922", "东方财富: 中证红利"),
    "sp500": ("1.513500", "东方财富: 标普500ETF博时代理"),
    "nasdaq100": ("1.513100", "东方财富: 纳指ETF国泰代理"),
}

_CACHE: tuple[float, MarketSnapshot] | None = None
CACHE_SECONDS = 15 * 60


def _fetch_eastmoney_klines(secid: str) -> List[dict]:
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={secid}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=1&beg=20190101&end=20500101"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("rc") != 0 or not payload.get("data", {}).get("klines"):
        raise RuntimeError(f"Eastmoney returned no data for {secid}")
    rows = []
    for raw in payload["data"]["klines"]:
        parts = raw.split(",")
        rows.append(
            {
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
            }
        )
    return rows


def _temperature_from_price(closes: List[float]) -> tuple[float, float, float, float]:
    if len(closes) < 60:
        raise RuntimeError("Not enough history to calculate temperature")
    current = closes[-1]
    ma_window = closes[-200:] if len(closes) >= 200 else closes
    ma200 = sum(ma_window) / len(ma_window)
    recent_window = closes[-756:] if len(closes) >= 756 else closes
    recent_high = max(recent_window)
    ma200_position = current / ma200 - 1
    drawdown = current / recent_high - 1

    returns = [
        math.log(closes[i] / closes[i - 1])
        for i in range(1, len(closes))
        if closes[i - 1] > 0 and closes[i] > 0
    ]
    recent_returns = returns[-63:] if len(returns) >= 63 else returns
    volatility = statistics.pstdev(recent_returns) * math.sqrt(252) if len(recent_returns) >= 2 else 0

    temperature = 50.0
    if ma200_position > 0.15:
        temperature += 18
    elif ma200_position > 0.08:
        temperature += 12
    elif ma200_position > 0.03:
        temperature += 6
    elif ma200_position < -0.15:
        temperature -= 18
    elif ma200_position < -0.08:
        temperature -= 12
    elif ma200_position < -0.03:
        temperature -= 6

    if drawdown > -0.03:
        temperature += 10
    elif drawdown < -0.30:
        temperature -= 24
    elif drawdown < -0.20:
        temperature -= 18
    elif drawdown < -0.10:
        temperature -= 10

    if volatility > 0.35:
        temperature += 4
    elif volatility < 0.12:
        temperature += 3

    return max(0, min(100, temperature)), ma200_position, drawdown, volatility


def fetch_live_market_snapshot(force_refresh: bool = False) -> MarketSnapshot:
    global _CACHE
    if _CACHE and not force_refresh and time.time() - _CACHE[0] < CACHE_SECONDS:
        return _CACHE[1]

    assets: List[MarketAssetSnapshot] = []
    errors: List[str] = []
    for asset_key, (secid, source_name) in EASTMONEY_SOURCES.items():
        try:
            rows = _fetch_eastmoney_klines(secid)
            closes = [row["close"] for row in rows]
            temperature, ma200_position, drawdown, volatility = _temperature_from_price(closes)
            latest = rows[-1]
            notes = [
                "价格、均线、回撤、波动来自真实K线；估值分位暂未接入。",
                "跨境资产使用境内ETF代理，可能包含汇率、溢价和跟踪误差。",
            ]
            if asset_key == "china_dividend":
                notes.append("红利温度暂基于价格技术指标，股息率分位后续接入。")
            assets.append(
                MarketAssetSnapshot(
                    asset_key=asset_key,
                    name=ASSET_NAMES[asset_key],
                    source=source_name,
                    source_symbol=secid,
                    as_of=latest["date"],
                    is_live=True,
                    price=latest["close"],
                    temperature=round(temperature, 1),
                    valuation_percentile=None,
                    ma200_position=round(ma200_position, 4),
                    drawdown=round(drawdown, 4),
                    volatility=round(volatility, 4),
                    dividend_yield_percentile=None,
                    data_quality="LIVE_PRICE_TECHNICAL_NO_VALUATION",
                    notes=notes,
                )
            )
        except Exception as exc:
            errors.append(f"{ASSET_NAMES[asset_key]}: {exc}")

    if len(assets) == len(EASTMONEY_SOURCES):
        snapshot = MarketSnapshot(
            generated_at=datetime.utcnow(),
            assets=assets,
            data_quality="LIVE_EASTMONEY_PRICE_TECHNICAL_NO_VALUATION",
            notes=[
                "已使用东方财富真实K线计算市场温度。",
                "估值分位、股息率分位暂未接入，因此温度不是完整估值模型。",
                "跨境资产采用境内ETF代理，结果可能受汇率和溢价影响。",
            ],
        )
    else:
        fallback = default_market_snapshot()
        snapshot = MarketSnapshot(
            generated_at=datetime.utcnow(),
            assets=fallback.assets,
            data_quality="PROXY_FALLBACK_LIVE_FETCH_FAILED",
            notes=[
                "真实行情源未完全可用，已回退到MVP代理数据。",
                *errors[:5],
            ],
        )

    _CACHE = (time.time(), snapshot)
    return snapshot
