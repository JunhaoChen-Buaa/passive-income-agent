from __future__ import annotations

import json
import math
import sqlite3
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Dict, Iterable, List, Optional, Tuple

from .models import AssetKey, HistoricalDataSourceStatus, HistoricalDataStatus
from .store import DB_PATH
from .strategies import ASSET_NAMES


@dataclass(frozen=True)
class HistorySource:
    asset_key: AssetKey
    name: str
    secid: str
    source: str
    note: str


@dataclass(frozen=True)
class MonthlyReturnDataset:
    months: List[str]
    returns: Dict[AssetKey, Dict[str, float]]
    data_quality: str
    notes: List[str]


HISTORY_SOURCES: Dict[AssetKey, HistorySource] = {
    "china_large": HistorySource(
        asset_key="china_large",
        name=ASSET_NAMES["china_large"],
        secid="blend:a500_hs300",
        source="Eastmoney blended daily kline: CSI A500 plus CSI 300 proxy if needed",
        note="优先使用中证A500指数历史；若A500源不可用或请求区间早于A500可用区间，才用沪深300代理补齐，并在回测边界中说明。",
    ),
    "china_mid": HistorySource(
        asset_key="china_mid",
        name=ASSET_NAMES["china_mid"],
        secid="1.000905",
        source="Eastmoney index daily kline: CSI 500",
        note="使用中证500指数日K线。",
    ),
    "china_dividend": HistorySource(
        asset_key="china_dividend",
        name=ASSET_NAMES["china_dividend"],
        secid="1.000922",
        source="Eastmoney index daily kline: CSI Dividend",
        note="使用中证红利指数日K线，未单独建模红利低波。",
    ),
    "sp500": HistorySource(
        asset_key="sp500",
        name=ASSET_NAMES["sp500"],
        secid="1.513500",
        source="Eastmoney adjusted daily kline: domestic S&P 500 ETF proxy",
        note="美股资产使用境内ETF前复权价格代理，结果会受汇率、溢价和跟踪误差影响。",
    ),
    "nasdaq100": HistorySource(
        asset_key="nasdaq100",
        name=ASSET_NAMES["nasdaq100"],
        secid="1.513100",
        source="Eastmoney adjusted daily kline: domestic Nasdaq 100 ETF proxy",
        note="纳指资产使用境内ETF前复权价格代理，结果会受汇率、溢价和跟踪误差影响。",
    ),
}


CHINA_LARGE_A500_SOURCE = HistorySource(
    asset_key="china_large",
    name="CSI A500",
    secid="1.000510",
    source="Eastmoney index daily kline: CSI A500",
    note="CSI A500 live segment.",
)

CHINA_LARGE_PROXY_SOURCE = HistorySource(
    asset_key="china_large",
    name="CSI 300",
    secid="1.000300",
    source="Eastmoney index daily kline: CSI 300 proxy before CSI A500 history",
    note="CSI 300 proxy segment before CSI A500 has enough history.",
)

_AUTO_REFRESH_LOCK = Lock()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS price_history (
            asset_key TEXT NOT NULL,
            date TEXT NOT NULL,
            close REAL NOT NULL,
            source TEXT NOT NULL,
            source_symbol TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            PRIMARY KEY (asset_key, date, source_symbol)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS history_refresh_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            refreshed_at TEXT NOT NULL,
            status TEXT NOT NULL,
            value TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _fetch_eastmoney_history(source: HistorySource) -> List[Tuple[str, float]]:
    url = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={source.secid}"
        "&fields1=f1,f2,f3,f4,f5,f6"
        "&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        "&klt=101&fqt=1&beg=20050101&end=20500101"
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    klines = payload.get("data", {}).get("klines") or []
    if payload.get("rc") != 0 or not klines:
        raise RuntimeError(f"Eastmoney returned no historical rows for {source.secid}")

    rows: List[Tuple[str, float]] = []
    for raw in klines:
        parts = raw.split(",")
        rows.append((parts[0], float(parts[2])))
    return rows


def _fetch_china_large_blended_history() -> List[Tuple[str, float]]:
    proxy_rows = _fetch_eastmoney_history(CHINA_LARGE_PROXY_SOURCE)
    try:
        a500_rows = _fetch_eastmoney_history(CHINA_LARGE_A500_SOURCE)
    except Exception:
        return proxy_rows

    if len(a500_rows) < 20:
        return proxy_rows

    a500_start = a500_rows[0][0]
    return [row for row in proxy_rows if row[0] < a500_start] + a500_rows


def _fetch_history_rows(source: HistorySource) -> List[Tuple[str, float]]:
    if source.asset_key == "china_large":
        return _fetch_china_large_blended_history()
    return _fetch_eastmoney_history(source)


def _save_rows(source: HistorySource, rows: List[Tuple[str, float]]) -> None:
    fetched_at = datetime.utcnow().isoformat()
    conn = _connect()
    conn.executemany(
        """
        INSERT INTO price_history (asset_key, date, close, source, source_symbol, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_key, date, source_symbol) DO UPDATE SET
            close = excluded.close,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        [(source.asset_key, date, close, source.source, source.secid, fetched_at) for date, close in rows],
    )
    conn.commit()
    conn.close()


def _cached_rows(asset_key: AssetKey) -> List[Tuple[str, float]]:
    source = HISTORY_SOURCES[asset_key]
    conn = _connect()
    rows = conn.execute(
        """
        SELECT date, close
        FROM price_history
        WHERE asset_key = ? AND source_symbol = ?
        ORDER BY date
        """,
        (asset_key, source.secid),
    ).fetchall()
    conn.close()
    return [(row["date"], float(row["close"])) for row in rows]


def _source_status(asset_key: AssetKey) -> HistoricalDataSourceStatus:
    source = HISTORY_SOURCES[asset_key]
    conn = _connect()
    row = conn.execute(
        """
        SELECT COUNT(*) AS row_count, MIN(date) AS start_date, MAX(date) AS end_date
        FROM price_history
        WHERE asset_key = ? AND source_symbol = ?
        """,
        (asset_key, source.secid),
    ).fetchone()
    conn.close()
    row_count = int(row["row_count"] or 0)
    enough = row_count >= 240
    notes = [source.note]
    if asset_key == "china_large":
        notes = ["优先使用中证A500指数历史；若A500源不可用或请求区间早于A500可用区间，才用沪深300代理补齐，并在回测边界中说明。"]
    return HistoricalDataSourceStatus(
        asset_key=asset_key,
        name=source.name,
        source=source.source,
        source_symbol=source.secid,
        row_count=row_count,
        start_date=row["start_date"] or "",
        end_date=row["end_date"] or "",
        is_cached=row_count > 0,
        data_quality="HISTORY_CACHE_READY" if enough else "HISTORY_CACHE_INCOMPLETE",
        notes=notes,
    )


def _latest_refresh_log() -> Optional[sqlite3.Row]:
    conn = _connect()
    row = conn.execute(
        """
        SELECT refreshed_at, status, value
        FROM history_refresh_log
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    conn.close()
    return row


def _append_refresh_log(status: str, payload: Dict[str, object]) -> str:
    refreshed_at = datetime.utcnow().isoformat()
    conn = _connect()
    conn.execute(
        "INSERT INTO history_refresh_log (refreshed_at, status, value) VALUES (?, ?, ?)",
        (refreshed_at, status, json.dumps(payload, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return refreshed_at


def _latest_source_end_date(status: HistoricalDataStatus) -> str:
    dates = [source.end_date for source in status.sources if source.end_date]
    return max(dates) if dates else ""


def history_status() -> HistoricalDataStatus:
    sources = [_source_status(asset_key) for asset_key in HISTORY_SOURCES]
    ready_count = sum(1 for source in sources if source.data_quality == "HISTORY_CACHE_READY")
    if ready_count == len(sources):
        quality = "HISTORY_CACHE_READY"
    elif ready_count:
        quality = "HISTORY_CACHE_PARTIAL"
    else:
        quality = "HISTORY_CACHE_EMPTY"
    return HistoricalDataStatus(
        generated_at=datetime.utcnow(),
        sources=sources,
        data_quality=quality,
        notes=[
            "这是回测引擎调用的本地历史行情缓存状态。",
            "刷新历史数据会从东方财富拉取日K线并写入本地 SQLite。",
            "跨境资产使用境内ETF代理；A股大盘优先使用中证A500指数历史，必要时才用沪深300代理并显式提示。",
        ],
    )


def history_status() -> HistoricalDataStatus:
    sources = [_source_status(asset_key) for asset_key in HISTORY_SOURCES]
    ready_count = sum(1 for source in sources if source.data_quality == "HISTORY_CACHE_READY")
    if ready_count == len(sources):
        quality = "HISTORY_CACHE_READY"
    elif ready_count:
        quality = "HISTORY_CACHE_PARTIAL"
    else:
        quality = "HISTORY_CACHE_EMPTY"
    return HistoricalDataStatus(
        generated_at=datetime.utcnow(),
        sources=sources,
        data_quality=quality,
        notes=[
            "这是回测引擎调用的本地历史行情缓存状态。",
            "刷新历史数据会从东方财富拉取日K线并写入本地 SQLite，回测默认使用最新缓存交易日。",
            "A股大盘优先使用中证A500指数历史；只有当A500源不可用或请求区间早于可用区间时，才用沪深300代理补齐并显式提示。",
            "跨境资产使用境内ETF前复权价格代理，会受汇率、溢价和跟踪误差影响。",
        ],
    )


def refresh_history_data(asset_keys: Optional[Iterable[AssetKey]] = None, trigger: str = "manual") -> HistoricalDataStatus:
    keys = list(asset_keys or HISTORY_SOURCES.keys())
    errors: Dict[str, str] = {}
    refreshed: Dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=min(5, len(keys))) as executor:
        futures = {
            executor.submit(_fetch_history_rows, HISTORY_SOURCES[key]): key
            for key in keys
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                rows = future.result()
                _save_rows(HISTORY_SOURCES[key], rows)
                refreshed[key] = len(rows)
            except Exception as exc:
                errors[key] = str(exc)

    status = history_status()
    message = (
        ("每日自动刷新已完成。" if not errors else "每日自动刷新部分完成，部分数据源失败。")
        if trigger == "auto"
        else ("手动刷新已完成。" if not errors else "手动刷新部分完成，部分数据源失败。")
    )
    payload = {
        "refreshed": refreshed,
        "errors": errors,
        "message": message,
        "status": status.model_dump(mode="json"),
    }
    refreshed_at = datetime.utcnow().isoformat()
    log_status = f"{trigger}_{'ok' if not errors else 'partial'}"
    conn = _connect()
    conn.execute(
        "INSERT INTO history_refresh_log (refreshed_at, status, value) VALUES (?, ?, ?)",
        (
            refreshed_at,
            log_status,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()

    if errors:
        status.notes.append("部分历史数据刷新失败：" + "；".join(f"{ASSET_NAMES[key]}: {message}" for key, message in errors.items()))
    if refreshed:
        status.notes.append("本次已刷新：" + "；".join(f"{ASSET_NAMES[key]} {count} 行" for key, count in refreshed.items()))
    status.auto_refresh_status = f"{trigger}_refreshed" if not errors else f"{trigger}_partial"
    status.auto_refresh_message = message
    status.last_refresh_at = refreshed_at
    return status


def history_status() -> HistoricalDataStatus:
    sources = [_source_status(asset_key) for asset_key in HISTORY_SOURCES]
    ready_count = sum(1 for source in sources if source.data_quality == "HISTORY_CACHE_READY")
    if ready_count == len(sources):
        quality = "HISTORY_CACHE_READY"
    elif ready_count:
        quality = "HISTORY_CACHE_PARTIAL"
    else:
        quality = "HISTORY_CACHE_EMPTY"

    latest_log = _latest_refresh_log()
    last_refresh_at = latest_log["refreshed_at"] if latest_log else ""
    refresh_status = latest_log["status"] if latest_log else "not_checked"
    refresh_message = ""
    if latest_log:
        try:
            payload = json.loads(latest_log["value"] or "{}")
            refresh_message = str(payload.get("message") or payload.get("auto_refresh_message") or "")
        except Exception:
            refresh_message = ""
    if not refresh_message and last_refresh_at:
        refresh_message = f"最近一次历史数据检查/刷新时间：{last_refresh_at[:19]}。"

    return HistoricalDataStatus(
        generated_at=datetime.utcnow(),
        sources=sources,
        data_quality=quality,
        notes=[
            "这是回测引擎调用的本地历史行情缓存状态。",
            "刷新历史数据会从东方财富拉取日K线并写入本地 SQLite，回测默认使用最新缓存交易日。",
            "A股大盘优先使用中证A500指数历史；只有当A500源不可用或请求区间早于可用区间时，才用沪深300代理补齐并显式提示。",
            "跨境资产使用境内ETF前复权价格代理，会受汇率、溢价和跟踪误差影响。",
        ],
        auto_refresh_status=refresh_status,
        auto_refresh_message=refresh_message,
        last_refresh_at=last_refresh_at,
    )


def maybe_refresh_history_data(trigger: str = "auto") -> HistoricalDataStatus:
    with _AUTO_REFRESH_LOCK:
        status = history_status()
        today = datetime.utcnow().date().isoformat()
        latest_end_date = _latest_source_end_date(status)
        latest_log = _latest_refresh_log()
        last_refresh_at = latest_log["refreshed_at"] if latest_log else ""

        if last_refresh_at.startswith(today):
            status.auto_refresh_status = "auto_skipped"
            status.auto_refresh_message = f"今日已经检查或刷新过历史数据（{last_refresh_at[:19]}），本次跳过。"
            return status

        should_refresh = (
            status.data_quality != "HISTORY_CACHE_READY"
            or not latest_end_date
            or latest_end_date < today
        )

        if should_refresh:
            refreshed = refresh_history_data(trigger=trigger)
            refreshed.auto_refresh_status = "auto_refreshed" if refreshed.data_quality == "HISTORY_CACHE_READY" else "auto_partial"
            refreshed.auto_refresh_message = f"每日自动检查发现缓存需要更新，已刷新到 { _latest_source_end_date(refreshed) or '未知日期' }。"
            return refreshed

        checked_at = _append_refresh_log(
            "auto_skipped",
            {
                "trigger": trigger,
                "message": f"缓存已到最新日期 {latest_end_date}，本次自动检查跳过刷新。",
                "status": status.model_dump(mode="json"),
            },
        )
        status.auto_refresh_status = "auto_skipped"
        status.auto_refresh_message = f"缓存已到最新日期 {latest_end_date}，本次自动检查跳过刷新。"
        status.last_refresh_at = checked_at
        return status


def _month_end_closes(rows: List[Tuple[str, float]]) -> Dict[str, float]:
    month_closes: Dict[str, float] = {}
    for date, close in rows:
        month_closes[date[:7]] = close
    return month_closes


def _monthly_returns(rows: List[Tuple[str, float]]) -> Dict[str, float]:
    month_closes = _month_end_closes(rows)
    months = sorted(month_closes)
    returns: Dict[str, float] = {}
    for index in range(1, len(months)):
        prev_close = month_closes[months[index - 1]]
        current_close = month_closes[months[index]]
        if prev_close > 0 and current_close > 0:
            returns[months[index]] = current_close / prev_close - 1
    return returns


def _active_assets(weights: Dict[AssetKey, float]) -> List[AssetKey]:
    return [asset for asset, weight in weights.items() if weight > 0.000001]


def load_monthly_return_dataset(
    weights: Dict[AssetKey, float],
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
    start_month: Optional[str] = None,
    end_month: Optional[str] = None,
    allow_refresh: bool = False,
) -> Optional[MonthlyReturnDataset]:
    active_assets = _active_assets(weights)
    if not active_assets:
        return None

    current_month = datetime.utcnow().strftime("%Y-%m")
    start_bound = start_month or f"{start_year or 2016}-01"
    end_bound = end_month or (f"{end_year}-12" if end_year else current_month)
    if start_bound > end_bound:
        start_bound, end_bound = end_bound, start_bound

    if allow_refresh:
        refresh_history_data(active_assets)

    returns_by_asset: Dict[AssetKey, Dict[str, float]] = {}
    asset_ranges: Dict[AssetKey, Tuple[str, str]] = {}
    missing: List[AssetKey] = []
    for asset_key in active_assets:
        rows = _cached_rows(asset_key)
        available_months = sorted(_month_end_closes(rows))
        if available_months:
            asset_ranges[asset_key] = (available_months[0], available_months[-1])
        returns = _monthly_returns(rows)
        filtered = {
            month: value
            for month, value in returns.items()
            if start_bound <= month <= end_bound
        }
        if len(filtered) < 36:
            missing.append(asset_key)
        returns_by_asset[asset_key] = filtered

    if missing:
        return None

    common_months = sorted(set.intersection(*(set(values) for values in returns_by_asset.values())))
    common_months = [month for month in common_months if start_bound <= month <= end_bound]
    if len(common_months) < 36:
        return None

    notes = [
        "回测使用东方财富历史日K线，按月末收盘价聚合为月度收益。",
        "每月买入、年度再平衡、分红再投资和手续费口径保持与策略规则一致；手续费仍按0简化。",
        "A股大盘优先使用中证A500指数历史；若A500源不可用或区间不足，才用沪深300代理补齐并显式提示；跨境资产用境内ETF前复权价格代理。",
        "结果仍会受到基金费率、汇率、溢价、跟踪误差、税费和实际成交日期影响。",
    ]
    notes.append(f"请求回测区间：{start_bound} 至 {end_bound}；实际共同可回测区间：{common_months[0]} 至 {common_months[-1]}。")
    for asset_key in active_assets:
        start, end = asset_ranges.get(asset_key, ("无缓存", "无缓存"))
        notes.append(f"{ASSET_NAMES[asset_key]} 可用月度行情：{start} 至 {end}。")
    if "china_large" in active_assets:
        notes.append("A股大盘口径：优先使用中证A500指数历史；若A500源不可用或请求区间早于可用区间，才用沪深300代理补齐并显式提示。")
    if end_bound >= current_month:
        notes.append("结束月份为当前月或未来月份时，回测使用当前缓存中的最新可用交易日收盘价，属于月内临时值。")
    return MonthlyReturnDataset(
        months=common_months,
        returns=returns_by_asset,
        data_quality="HISTORICAL_EASTMONEY_ADJUSTED_MONTHLY",
        notes=notes,
    )


def annualized_volatility(monthly_returns: List[float]) -> float:
    return statistics.pstdev(monthly_returns) * math.sqrt(12) if len(monthly_returns) >= 2 else 0.0


def wait_a_moment_for_rate_limit() -> None:
    time.sleep(0.05)
