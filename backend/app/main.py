from __future__ import annotations

import os
from pathlib import Path
from threading import Thread
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_provider import explain_with_provider, generate_personal_strategy, provider_out
from .backtest import run_backtest
from .data_sources import fetch_live_market_snapshot
from .history_data import history_status, maybe_refresh_history_data, refresh_history_data
from .models import (
    AIExplainRequest,
    AIExplainResponse,
    BacktestRequest,
    BacktestResult,
    CashPool,
    FundPoolItem,
    HistoricalDataStatus,
    InvestmentRecord,
    MonthlyPlan,
    MonthlyPlanRequest,
    PersonalStrategyRequest,
    PersonalStrategyResponse,
    Profile,
    ProviderConfigIn,
    ProviderConfigOut,
    StrategyTemplate,
)
from .rules import generate_monthly_plan
from .store import add_record, get_value, list_records, set_value, update_record_execution
from .strategies import STRATEGIES, default_fund_pool, get_strategy


app = FastAPI(title="Index Fund Passive Income Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _startup_history_check() -> None:
    try:
        maybe_refresh_history_data(trigger="startup")
    except Exception:
        pass


@app.on_event("startup")
def startup_history_auto_refresh() -> None:
    Thread(target=_startup_history_check, daemon=True).start()


class ExecutionUpdate(BaseModel):
    executed: bool
    execution_note: str = ""


def _get_profile() -> Profile:
    value = get_value("profile")
    return Profile(**value) if value else Profile()


def _get_cash_pool() -> CashPool:
    value = get_value("cash_pool")
    return CashPool(**value) if value else CashPool()


def _get_provider_config() -> ProviderConfigIn:
    value = get_value("provider_config")
    if value:
        return ProviderConfigIn(**value)
    return ProviderConfigIn(
        provider=os.getenv("AI_PROVIDER", os.getenv("DEEPSEEK_PROVIDER", "deepseek")),
        base_url=os.getenv("AI_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")),
        api_key=os.getenv("AI_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
        model=os.getenv("AI_MODEL", os.getenv("DEEPSEEK_MODEL", "deepseek-chat")),
        temperature=float(os.getenv("AI_TEMPERATURE", "0.3")),
    )


def _get_personal_strategy() -> StrategyTemplate | None:
    value = get_value("personal_strategy") or get_value("custom_strategy")
    return StrategyTemplate(**value) if value else None


def _run_personal_backtest(profile: Profile, strategy: StrategyTemplate, refresh_history: bool = False) -> BacktestResult:
    result = run_backtest(
        BacktestRequest(
            strategy_id="balanced_compound",
            initial_capital=profile.lump_sum_capital,
            monthly_contribution=profile.monthly_contribution,
            custom_weights=strategy.weights,
            data_mode="history" if refresh_history else "auto",
            refresh_history=refresh_history,
        )
    )
    return result.model_copy(update={"strategy_id": strategy.id, "strategy_name": strategy.name})


@app.get("/api/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "index-fund-agent"}


@app.get("/api/profile", response_model=Profile)
def get_profile() -> Profile:
    return _get_profile()


@app.put("/api/profile", response_model=Profile)
def put_profile(profile: Profile) -> Profile:
    set_value("profile", profile)
    return profile


@app.get("/api/strategies", response_model=List[StrategyTemplate])
def get_strategies() -> List[StrategyTemplate]:
    personal_strategy = _get_personal_strategy()
    return [*STRATEGIES, personal_strategy] if personal_strategy else STRATEGIES


@app.get("/api/strategies/{strategy_id}", response_model=StrategyTemplate)
def strategy_detail(strategy_id: str) -> StrategyTemplate:
    if strategy_id == "personal_custom":
        personal_strategy = _get_personal_strategy()
        if personal_strategy:
            return personal_strategy
    return get_strategy(strategy_id)


@app.put("/api/strategies/custom", response_model=StrategyTemplate)
def put_custom_strategy(strategy: StrategyTemplate) -> StrategyTemplate:
    strategy = strategy.model_copy(update={"id": "personal_custom", "is_personalized": True})
    set_value("personal_strategy", strategy)
    return strategy


@app.post("/api/personal-strategy/generate", response_model=PersonalStrategyResponse)
def post_personal_strategy(request: PersonalStrategyRequest) -> PersonalStrategyResponse:
    response = generate_personal_strategy(request, _get_provider_config())
    set_value("personal_strategy", response.strategy)
    profile = request.profile.model_copy(update={"selected_strategy_id": response.strategy.id})
    set_value("profile", profile)
    backtest = _run_personal_backtest(profile, response.strategy, refresh_history=True)
    return response.model_copy(update={"backtest": backtest})


@app.post("/api/backtest", response_model=BacktestResult)
def post_backtest(request: BacktestRequest) -> BacktestResult:
    if request.strategy_id == "personal_custom":
        personal_strategy = _get_personal_strategy()
        if not personal_strategy:
            raise HTTPException(status_code=404, detail="Personal strategy not found")
        personal_request = request.model_copy(
            update={
                "strategy_id": "balanced_compound",
                "custom_weights": personal_strategy.weights,
            }
        )
        result = run_backtest(personal_request)
        return result.model_copy(update={"strategy_id": personal_strategy.id, "strategy_name": personal_strategy.name})
    return run_backtest(request)


@app.get("/api/backtest/default-comparison", response_model=List[BacktestResult])
def default_comparison() -> List[BacktestResult]:
    profile = _get_profile()
    results = [
        run_backtest(
            BacktestRequest(
                strategy_id=strategy.id,
                initial_capital=profile.lump_sum_capital,
                monthly_contribution=profile.monthly_contribution,
            )
        )
        for strategy in STRATEGIES
    ]
    personal_strategy = _get_personal_strategy()
    if personal_strategy:
        results.append(_run_personal_backtest(profile, personal_strategy))
    return results


@app.get("/api/fund-pool", response_model=List[FundPoolItem])
def get_fund_pool() -> List[FundPoolItem]:
    value = get_value("fund_pool")
    if not value:
        return default_fund_pool()
    return [FundPoolItem(**item) for item in value]


@app.put("/api/fund-pool", response_model=List[FundPoolItem])
def put_fund_pool(pool: List[FundPoolItem]) -> List[FundPoolItem]:
    set_value("fund_pool", pool)
    return pool


@app.get("/api/cash-pool", response_model=CashPool)
def get_cash_pool() -> CashPool:
    return _get_cash_pool()


@app.put("/api/cash-pool", response_model=CashPool)
def put_cash_pool(cash_pool: CashPool) -> CashPool:
    set_value("cash_pool", cash_pool)
    return cash_pool


@app.get("/api/market-snapshot")
def get_market_snapshot(force_refresh: bool = False):
    return fetch_live_market_snapshot(force_refresh=force_refresh)


@app.get("/api/history-data/status", response_model=HistoricalDataStatus)
def get_history_data_status() -> HistoricalDataStatus:
    return history_status()


@app.post("/api/history-data/refresh", response_model=HistoricalDataStatus)
def post_history_data_refresh() -> HistoricalDataStatus:
    return refresh_history_data()


@app.post("/api/history-data/auto-refresh", response_model=HistoricalDataStatus)
def post_history_data_auto_refresh() -> HistoricalDataStatus:
    return maybe_refresh_history_data(trigger="frontend")


@app.post("/api/monthly-plan", response_model=MonthlyPlan)
def post_monthly_plan(request: MonthlyPlanRequest) -> MonthlyPlan:
    profile = request.profile or _get_profile()
    cash_pool = request.cash_pool or _get_cash_pool()
    market = fetch_live_market_snapshot()
    strategy_id = request.strategy_id or profile.selected_strategy_id
    personal_strategy = _get_personal_strategy() if strategy_id == "personal_custom" else None
    return generate_monthly_plan(
        profile=profile,
        cash_pool=cash_pool,
        strategy_id=strategy_id,
        custom_weights=request.custom_weights or (personal_strategy.weights if personal_strategy else None),
        market=market,
        strategy_template=personal_strategy,
    )


@app.post("/api/ai-explain", response_model=AIExplainResponse)
def post_ai_explain(request: AIExplainRequest) -> AIExplainResponse:
    return explain_with_provider(request.plan, _get_provider_config())


@app.get("/api/records")
def records():
    return list_records()


@app.post("/api/records")
def create_record(record: InvestmentRecord):
    record_id, duplicate = add_record(record)
    return {"id": record_id, "duplicate": duplicate}


@app.put("/api/records/{record_id}/execution")
def put_record_execution(record_id: int, update: ExecutionUpdate):
    if not update_record_execution(record_id, update.executed, update.execution_note):
        raise HTTPException(status_code=404, detail="Record not found")
    return {"ok": True}


@app.get("/api/provider-config", response_model=ProviderConfigOut)
def get_provider_config() -> ProviderConfigOut:
    return provider_out(_get_provider_config())


@app.put("/api/provider-config", response_model=ProviderConfigOut)
def put_provider_config(config: ProviderConfigIn) -> ProviderConfigOut:
    previous = _get_provider_config()
    if not config.api_key and previous.api_key:
        config.api_key = previous.api_key
    set_value("provider_config", config)
    return provider_out(config)


def _mount_frontend() -> None:
    default_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    dist_dir = Path(os.getenv("FRONTEND_DIST_DIR", str(default_dist)))
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")


_mount_frontend()
