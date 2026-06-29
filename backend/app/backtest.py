from __future__ import annotations

import math
import statistics
from datetime import datetime
from typing import Dict, List, Tuple

from .history_data import history_status, load_monthly_return_dataset
from .models import AssetKey, BacktestRequest, BacktestResult, EquityPoint
from .sample_data import PROXY_YEARLY_RETURNS
from .strategies import ASSET_NAMES, get_strategy, normalize_weights


def _monthly_return(annual_return: float) -> float:
    if annual_return <= -0.999:
        return -0.999
    return (1 + annual_return) ** (1 / 12) - 1


def _xirr_monthly(cashflows: List[float]) -> float:
    low, high = -0.99, 10.0
    for _ in range(120):
        mid = (low + high) / 2
        npv = sum(cf / ((1 + mid) ** i) for i, cf in enumerate(cashflows))
        if npv > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _longest_recovery_months(nav_values: List[float]) -> int:
    peak = nav_values[0]
    drawdown_start = None
    longest = 0
    for index, nav in enumerate(nav_values):
        if nav >= peak:
            if drawdown_start is not None:
                longest = max(longest, index - drawdown_start)
                drawdown_start = None
            peak = nav
        elif drawdown_start is None:
            drawdown_start = index
    if drawdown_start is not None:
        longest = max(longest, len(nav_values) - 1 - drawdown_start)
    return longest


def _max_drawdown(nav_values: List[float]) -> float:
    peak = nav_values[0]
    max_dd = 0.0
    for nav in nav_values:
        peak = max(peak, nav)
        if peak > 0:
            max_dd = min(max_dd, nav / peak - 1)
    return max_dd


def _annual_returns(monthly_returns: List[Tuple[str, float]]) -> Dict[str, float]:
    years: Dict[str, List[float]] = {}
    for date, value in monthly_returns:
        years.setdefault(date[:4], []).append(value)
    return {
        year: math.prod(1 + monthly for monthly in values) - 1
        for year, values in years.items()
    }


def _request_start_month(request: BacktestRequest) -> str:
    return request.start_month or f"{request.start_year}-01"


def _request_end_month(request: BacktestRequest) -> str:
    return request.end_month or datetime.utcnow().strftime("%Y-%m")


def _history_gap_notes(request: BacktestRequest, weights: Dict[AssetKey, float]) -> List[str]:
    start_month = _request_start_month(request)
    end_month = _request_end_month(request)
    active_assets = {asset for asset, weight in weights.items() if weight > 0.000001}
    status = history_status()
    notes = [f"请求回测区间：{start_month} 至 {end_month}。历史数据不足时不会静默补齐，会在这里列出缺口。"]
    for source in status.sources:
        if source.asset_key in active_assets:
            notes.append(
                f"{source.name} 当前缓存：{source.start_date or '无'} 至 {source.end_date or '无'}；"
                f"来源：{source.source}；状态：{source.data_quality}。"
            )
    if "china_large" in active_assets:
        notes.append("A股大盘口径：A500可用区间使用A500，A500成立前使用沪深300代理；不是纯A500全历史。")
    return notes


def _run_with_monthly_returns(request: BacktestRequest) -> BacktestResult | None:
    strategy = get_strategy(request.strategy_id)
    weights = normalize_weights(request.custom_weights or strategy.weights)
    dataset = load_monthly_return_dataset(
        weights=weights,
        start_month=_request_start_month(request),
        end_month=_request_end_month(request),
        allow_refresh=request.refresh_history,
    )
    if not dataset:
        return None

    holdings = {
        asset: request.initial_capital * weights.get(asset, 0)
        for asset in ASSET_NAMES.keys()
    }
    total_contributed = request.initial_capital
    portfolio_value = sum(holdings.values())
    nav = 1.0
    equity_curve = [EquityPoint(date=dataset.months[0], value=round(portfolio_value, 2), nav=nav)]
    monthly_portfolio_returns: List[Tuple[str, float]] = []
    cashflows = [-request.initial_capital]

    for index, month in enumerate(dataset.months):
        if index > 0 and month.endswith("-01"):
            portfolio_value = sum(holdings.values())
            holdings = {
                asset: portfolio_value * weights.get(asset, 0)
                for asset in ASSET_NAMES.keys()
            }

        start_value = sum(holdings.values())
        contribution = request.monthly_contribution
        if contribution > 0:
            for asset, weight in weights.items():
                holdings[asset] += contribution * weight
            total_contributed += contribution
            cashflows.append(-contribution)

        for asset in ASSET_NAMES.keys():
            month_return = dataset.returns.get(asset, {}).get(month, 0.0)
            holdings[asset] *= 1 + month_return

        end_value = sum(holdings.values())
        if start_value > 0:
            portfolio_return = (end_value - contribution - start_value) / start_value
        else:
            portfolio_return = 0.0
        nav *= 1 + portfolio_return
        monthly_portfolio_returns.append((month, portfolio_return))
        equity_curve.append(EquityPoint(date=month, value=round(end_value, 2), nav=round(nav, 4)))

    final_value = sum(holdings.values())
    cashflows.append(final_value)
    monthly_irr = _xirr_monthly(cashflows)
    annualized_return = (1 + monthly_irr) ** 12 - 1
    monthly_values = [ret for _, ret in monthly_portfolio_returns]
    annualized_volatility = statistics.pstdev(monthly_values) * math.sqrt(12) if monthly_values else 0
    nav_values = [point.nav for point in equity_curve]
    annuals = _annual_returns(monthly_portfolio_returns)
    worst_year, worst_return = min(annuals.items(), key=lambda item: item[1])

    trailing_returns: Dict[str, float] = {}
    for label, months in {"3y": 36, "5y": 60, "10y": 120}.items():
        if len(nav_values) > months:
            trailing_returns[label] = nav_values[-1] / nav_values[-1 - months] - 1
        else:
            trailing_returns[label] = 0

    return BacktestResult(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        annualized_return=round(annualized_return, 4),
        max_drawdown=round(_max_drawdown(nav_values), 4),
        annualized_volatility=round(annualized_volatility, 4),
        worst_year=worst_year,
        worst_year_return=round(worst_return, 4),
        longest_recovery_months=_longest_recovery_months(nav_values),
        trailing_returns={key: round(value, 4) for key, value in trailing_returns.items()},
        final_value=round(final_value, 2),
        total_contributed=round(total_contributed, 2),
        equity_curve=equity_curve,
        data_quality=dataset.data_quality,
        notes=dataset.notes,
    )


def _run_proxy_backtest(
    request: BacktestRequest,
    data_quality: str = "MVP_PROXY_ANNUAL_DATA",
    extra_notes: List[str] | None = None,
) -> BacktestResult:
    strategy = get_strategy(request.strategy_id)
    weights = normalize_weights(request.custom_weights or strategy.weights)
    start_year = int(_request_start_month(request)[:4])
    end_year = int(_request_end_month(request)[:4])
    years = range(start_year, end_year + 1)

    holdings = {
        asset: request.initial_capital * weights.get(asset, 0)
        for asset in ASSET_NAMES.keys()
    }
    total_contributed = request.initial_capital
    portfolio_value = sum(holdings.values())
    nav = 1.0
    equity_curve = [EquityPoint(date=f"{start_year}-00", value=portfolio_value, nav=nav)]
    monthly_portfolio_returns: List[Tuple[str, float]] = []
    cashflows = [-request.initial_capital]

    for year in years:
        if year != start_year:
            portfolio_value = sum(holdings.values())
            holdings = {
                asset: portfolio_value * weights.get(asset, 0)
                for asset in ASSET_NAMES.keys()
            }

        for month in range(1, 13):
            start_value = sum(holdings.values())
            contribution = request.monthly_contribution
            if contribution > 0:
                for asset, weight in weights.items():
                    holdings[asset] += contribution * weight
                total_contributed += contribution
                cashflows.append(-contribution)

            for asset in ASSET_NAMES.keys():
                annual = PROXY_YEARLY_RETURNS[asset].get(year, 0)
                holdings[asset] *= 1 + _monthly_return(annual)

            end_value = sum(holdings.values())
            if start_value > 0:
                month_return = (end_value - contribution - start_value) / start_value
            else:
                month_return = 0.0
            nav *= 1 + month_return
            date = f"{year}-{month:02d}"
            monthly_portfolio_returns.append((date, month_return))
            equity_curve.append(EquityPoint(date=date, value=round(end_value, 2), nav=round(nav, 4)))

    final_value = sum(holdings.values())
    cashflows.append(final_value)
    monthly_irr = _xirr_monthly(cashflows)
    annualized_return = (1 + monthly_irr) ** 12 - 1
    monthly_values = [ret for _, ret in monthly_portfolio_returns]
    annualized_volatility = statistics.pstdev(monthly_values) * math.sqrt(12) if monthly_values else 0
    nav_values = [point.nav for point in equity_curve]
    annuals = _annual_returns(monthly_portfolio_returns)
    worst_year, worst_return = min(annuals.items(), key=lambda item: item[1])

    trailing_returns: Dict[str, float] = {}
    for label, months in {"3y": 36, "5y": 60, "10y": 120}.items():
        if len(nav_values) > months:
            trailing_returns[label] = nav_values[-1] / nav_values[-1 - months] - 1
        else:
            trailing_returns[label] = 0

    return BacktestResult(
        strategy_id=strategy.id,
        strategy_name=strategy.name,
        annualized_return=round(annualized_return, 4),
        max_drawdown=round(_max_drawdown(nav_values), 4),
        annualized_volatility=round(annualized_volatility, 4),
        worst_year=worst_year,
        worst_year_return=round(worst_return, 4),
        longest_recovery_months=_longest_recovery_months(nav_values),
        trailing_returns={key: round(value, 4) for key, value in trailing_returns.items()},
        final_value=round(final_value, 2),
        total_contributed=round(total_contributed, 2),
        equity_curve=equity_curve,
        data_quality=data_quality,
        notes=[
            "当前回测使用内置年度代理数据，主要用于比较策略风险收益轮廓。",
            "真实基金收益会受费率、汇率、跟踪误差、税费和分红处理影响。",
            "A500 历史不足时可用沪深300作为大盘代理，页面需保留代理标记。",
            *_history_gap_notes(request, weights),
            *(extra_notes or []),
        ],
    )


def run_backtest(request: BacktestRequest) -> BacktestResult:
    if request.data_mode != "proxy":
        historical = _run_with_monthly_returns(request)
        if historical:
            return historical
        if request.data_mode == "history" or request.refresh_history:
            return _run_proxy_backtest(
                request,
                data_quality="PROXY_FALLBACK_HISTORY_DATA_UNAVAILABLE",
                extra_notes=["历史行情工具未能取得足够月度数据，本次临时降级为代理年度数据；请先刷新历史数据后再复核。"],
            )

    return _run_proxy_backtest(request)
