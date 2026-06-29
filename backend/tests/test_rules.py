from app.backtest import run_backtest
from app.models import BacktestRequest, CashPool, Profile
from app.rules import generate_monthly_plan, multiplier_for_temperature, temperature_band
from app.strategies import STRATEGIES


def test_strategy_weights_sum_to_one():
    for strategy in STRATEGIES:
        assert abs(sum(strategy.weights.values()) - 1) < 0.0001


def test_temperature_bands_and_multipliers():
    assert temperature_band(20) == "极冷"
    assert temperature_band(50) == "正常"
    assert temperature_band(85) == "极热"
    assert multiplier_for_temperature(20) > multiplier_for_temperature(50)
    assert multiplier_for_temperature(85) < 1


def test_cash_floor_blocks_new_investment():
    profile = Profile(current_cash=30000, emergency_cash_floor=30000)
    plan = generate_monthly_plan(profile, CashPool())
    assert plan.suggested_total_buy == 0
    assert plan.multiplier == 0


def test_monthly_plan_generates_allocations():
    profile = Profile(current_cash=130000, emergency_cash_floor=30000)
    plan = generate_monthly_plan(profile, CashPool())
    assert plan.suggested_total_buy > 0
    assert len(plan.allocations) == 5
    assert round(sum(item.amount for item in plan.allocations), 2) == plan.suggested_total_buy


def test_backtest_has_risk_metrics():
    result = run_backtest(BacktestRequest(strategy_id="tech_growth", data_mode="proxy"))
    assert result.final_value > 0
    assert result.max_drawdown < 0
    assert result.annualized_volatility > 0
    assert result.data_quality == "MVP_PROXY_ANNUAL_DATA"
