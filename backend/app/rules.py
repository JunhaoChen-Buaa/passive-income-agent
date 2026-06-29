from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from .models import (
    AssetKey,
    CashPool,
    MarketAssetSnapshot,
    MarketSnapshot,
    MonthlyAllocation,
    MonthlyPlan,
    Profile,
)
from .strategies import ASSET_NAMES, StrategyTemplate, get_strategy, normalize_weights


def default_market_snapshot() -> MarketSnapshot:
    assets = [
        MarketAssetSnapshot(
            asset_key="china_large",
            name=ASSET_NAMES["china_large"],
            price=1000,
            temperature=42,
            valuation_percentile=38,
            ma200_position=-0.03,
            drawdown=-0.15,
            volatility=0.18,
            data_quality="代理指标",
            notes=["A500 历史不足时以沪深300代表A股大盘温度。"],
        ),
        MarketAssetSnapshot(
            asset_key="china_mid",
            name=ASSET_NAMES["china_mid"],
            price=1000,
            temperature=38,
            valuation_percentile=32,
            ma200_position=-0.05,
            drawdown=-0.20,
            volatility=0.24,
            data_quality="代理指标",
            notes=["中盘弹性更高，低温不等于低风险。"],
        ),
        MarketAssetSnapshot(
            asset_key="china_dividend",
            name=ASSET_NAMES["china_dividend"],
            price=1000,
            temperature=48,
            valuation_percentile=45,
            ma200_position=0.02,
            drawdown=-0.08,
            volatility=0.14,
            dividend_yield_percentile=68,
            data_quality="代理指标",
            notes=["红利仍是股票资产，高股息需要排查行业集中和盈利下滑。"],
        ),
        MarketAssetSnapshot(
            asset_key="sp500",
            name=ASSET_NAMES["sp500"],
            price=1000,
            temperature=72,
            valuation_percentile=76,
            ma200_position=0.09,
            drawdown=-0.04,
            volatility=0.17,
            data_quality="代理指标",
            notes=["美股核心资产质量高，但高估值阶段不宜追涨。"],
        ),
        MarketAssetSnapshot(
            asset_key="nasdaq100",
            name=ASSET_NAMES["nasdaq100"],
            price=1000,
            temperature=78,
            valuation_percentile=82,
            ma200_position=0.12,
            drawdown=-0.06,
            volatility=0.26,
            data_quality="代理指标",
            notes=["纳指弹性强，回撤也通常更深。"],
        ),
    ]
    return MarketSnapshot(
        generated_at=datetime.utcnow(),
        assets=assets,
        data_quality="MVP_PROXY_METRICS",
        notes=[
            "MVP 默认使用代理市场温度，后续可接入 AkShare、yfinance 或手动录入。",
            "数据不足时必须显示质量标签，不把代理指标包装成精确结论。",
        ],
    )


def temperature_band(temperature: float) -> str:
    if temperature < 25:
        return "极冷"
    if temperature < 45:
        return "偏冷"
    if temperature < 65:
        return "正常"
    if temperature < 80:
        return "偏热"
    return "极热"


def multiplier_for_temperature(temperature: float) -> float:
    if temperature < 25:
        return 1.75
    if temperature < 45:
        return 1.35
    if temperature < 65:
        return 1.0
    if temperature < 80:
        return 0.7
    return 0.5


def _weighted_temperature(weights: Dict[AssetKey, float], market: MarketSnapshot) -> float:
    temps = {asset.asset_key: asset.temperature for asset in market.assets}
    return sum(temps.get(asset, 50) * weight for asset, weight in weights.items())


def _base_monthly_amount(profile: Profile, cash_pool: CashPool) -> float:
    queue_release = cash_pool.queue_cash / max(profile.investment_months, 1)
    return profile.monthly_contribution + queue_release


def _cash_after_buy(cash_pool: CashPool, buy_amount: float, base_amount: float) -> CashPool:
    queue_spend = min(cash_pool.queue_cash, min(buy_amount, base_amount))
    extra = max(0.0, buy_amount - queue_spend)
    opportunity_spend = min(cash_pool.opportunity_cash, extra)
    return CashPool(
        emergency_cash=cash_pool.emergency_cash,
        queue_cash=round(max(0.0, cash_pool.queue_cash - queue_spend), 2),
        opportunity_cash=round(max(0.0, cash_pool.opportunity_cash - opportunity_spend), 2),
        parking_tool=cash_pool.parking_tool,
        notes=cash_pool.notes,
    )


def _rebalance_notes(profile: Profile, strategy: StrategyTemplate) -> List[str]:
    if not profile.holdings:
        return ["尚未录入各指数持仓，MVP 暂不生成卖出型再平衡建议。"]
    total = sum(value for value in profile.holdings.values() if value > 0)
    if total <= 0:
        return ["持仓金额为 0，暂不需要再平衡。"]
    notes: List[str] = []
    for asset, target in strategy.weights.items():
        actual = profile.holdings.get(asset, 0) / total
        drift = actual - target
        if abs(drift) >= 0.05:
            direction = "超配" if drift > 0 else "低配"
            notes.append(f"{ASSET_NAMES[asset]} 当前{direction} {abs(drift):.1%}，优先用新增资金修正。")
    return notes or ["当前持仓偏离未超过 5%，不触发再平衡提醒。"]


def generate_monthly_plan(
    profile: Profile,
    cash_pool: CashPool,
    strategy_id: str | None = None,
    custom_weights: Dict[AssetKey, float] | None = None,
    market: MarketSnapshot | None = None,
    strategy_template: StrategyTemplate | None = None,
) -> MonthlyPlan:
    strategy = strategy_template or get_strategy(strategy_id or profile.selected_strategy_id)
    weights = normalize_weights(custom_weights or strategy.weights)
    market = market or default_market_snapshot()
    avg_temperature = _weighted_temperature(weights, market)
    band = temperature_band(avg_temperature)
    multiplier = multiplier_for_temperature(avg_temperature)
    base_amount = _base_monthly_amount(profile, cash_pool)

    available_after_floor = max(0.0, profile.current_cash - profile.emergency_cash_floor)
    risk_notes = [
        "本工具不自动下单，金额建议只用于纪律辅助。",
        "指数基金不是无风险资产，历史回测不代表未来收益。",
    ]
    if profile.current_cash <= profile.emergency_cash_floor:
        suggested_total = 0.0
        multiplier = 0.0
        risk_notes.append("当前现金低于或等于应急现金底线，本月暂停新增投资。")
    else:
        suggested_total = min(base_amount * multiplier, available_after_floor)

    snapshots = {asset.asset_key: asset for asset in market.assets}
    allocations: List[MonthlyAllocation] = []
    running_total = 0.0
    weight_items = list(weights.items())
    for index, (asset, weight) in enumerate(weight_items):
        if index == len(weight_items) - 1:
            amount = round(suggested_total - running_total, 2)
        else:
            amount = round(suggested_total * weight, 2)
            running_total += amount
        allocations.append(
            MonthlyAllocation(
                asset_key=asset,
                name=ASSET_NAMES[asset],
                target_weight=weight,
                amount=amount,
                temperature=snapshots.get(asset).temperature if snapshots.get(asset) else 50,
                multiplier=multiplier,
            )
        )

    if avg_temperature >= 80:
        risk_notes.append("市场温度极热：只降低新增买入，不做清仓式逃顶。")
    if avg_temperature < 45:
        risk_notes.append("市场偏冷：允许多买一点，但仍保留应急现金和机会资金边界。")
    if weights.get("nasdaq100", 0) >= 0.35:
        risk_notes.append("纳斯达克100权重较高，需确认能承受较深回撤。")
    if weights.get("china_dividend", 0) >= 0.35:
        risk_notes.append("红利权重较高：它是股票资产，不等同于债券或稳定收息产品。")

    return MonthlyPlan(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        generated_at=datetime.utcnow(),
        average_temperature=round(avg_temperature, 1),
        temperature_band=band,
        base_amount=round(base_amount, 2),
        multiplier=round(multiplier, 2),
        suggested_total_buy=round(suggested_total, 2),
        allocations=allocations,
        cash_after=_cash_after_buy(cash_pool, suggested_total, base_amount),
        risk_notes=risk_notes,
        rebalance_notes=_rebalance_notes(profile, strategy),
        education_message=(
            "先选长期策略，再管理现金池，按月把现金流转成指数资产；"
            "市场低温时多买一点，高温时少买一点，但不幻想精准抄底逃顶。"
        ),
        data_quality_status=market.data_quality,
    )
