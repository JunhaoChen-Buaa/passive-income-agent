from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


AssetKey = Literal[
    "china_large",
    "china_mid",
    "china_dividend",
    "sp500",
    "nasdaq100",
]


class Profile(BaseModel):
    lump_sum_capital: float = Field(default=100000, ge=0)
    monthly_contribution: float = Field(default=1000, ge=0)
    emergency_cash_floor: float = Field(default=30000, ge=0)
    current_cash: float = Field(default=130000, ge=0)
    risk_preference: Literal["conservative", "balanced", "growth"] = "balanced"
    investment_months: int = Field(default=12, ge=1, le=36)
    selected_strategy_id: str = "balanced_compound"
    holdings: Dict[AssetKey, float] = Field(default_factory=dict)


class StrategyTemplate(BaseModel):
    id: str
    name: str
    level: str
    positioning: str
    audience: str
    return_sources: List[str]
    risks: List[str]
    weights: Dict[AssetKey, float]
    is_personalized: bool = False


class PersonalStrategyRequest(BaseModel):
    profile: Profile = Field(default_factory=Profile)
    goals: str = "长期积累被动收入，优先坚持定投纪律。"
    investment_horizon: str = "10年以上"
    drawdown_tolerance: str = "中等，可以接受阶段性回撤但不希望过度激进。"
    preferences: str = "只买指数基金，偏好宽基、红利和全球分散。"
    template_hint: str = "balanced_compound"


class PersonalStrategyResponse(BaseModel):
    strategy: StrategyTemplate
    explanation: str
    provider_used: str
    fallback: bool
    backtest: Optional["BacktestResult"] = None


class BacktestRequest(BaseModel):
    strategy_id: str = "balanced_compound"
    initial_capital: float = Field(default=100000, ge=0)
    monthly_contribution: float = Field(default=1000, ge=0)
    start_year: int = 2016
    end_year: int = 2025
    start_month: Optional[str] = None
    end_month: Optional[str] = None
    custom_weights: Optional[Dict[AssetKey, float]] = None
    data_mode: Literal["auto", "history", "proxy"] = "auto"
    refresh_history: bool = False


class EquityPoint(BaseModel):
    date: str
    value: float
    nav: float


class BacktestResult(BaseModel):
    strategy_id: str
    strategy_name: str
    annualized_return: float
    max_drawdown: float
    annualized_volatility: float
    worst_year: str
    worst_year_return: float
    longest_recovery_months: int
    trailing_returns: Dict[str, float]
    final_value: float
    total_contributed: float
    equity_curve: List[EquityPoint]
    data_quality: str
    notes: List[str]


class FundPoolItem(BaseModel):
    asset_key: AssetKey
    index_name: str
    fund_code: str = ""
    target_weight: float = Field(default=0, ge=0, le=1)
    asset_class: str
    enabled: bool = True


class CashPool(BaseModel):
    emergency_cash: float = Field(default=30000, ge=0)
    queue_cash: float = Field(default=70000, ge=0)
    opportunity_cash: float = Field(default=20000, ge=0)
    parking_tool: str = "货币基金 / 现金管理 / 银行低风险流动性产品"
    notes: str = "现金池用于保流动性、等待定投节奏和低温机会；不描述为保本。"


class MarketAssetSnapshot(BaseModel):
    asset_key: AssetKey
    name: str
    source: str = "proxy"
    source_symbol: str = ""
    as_of: str = ""
    is_live: bool = False
    price: float
    temperature: float = Field(ge=0, le=100)
    valuation_percentile: Optional[float] = Field(default=None, ge=0, le=100)
    ma200_position: float
    drawdown: float
    volatility: float
    dividend_yield_percentile: Optional[float] = Field(default=None, ge=0, le=100)
    data_quality: str
    notes: List[str] = Field(default_factory=list)


class MarketSnapshot(BaseModel):
    generated_at: datetime
    assets: List[MarketAssetSnapshot]
    data_quality: str
    notes: List[str]


class HistoricalDataSourceStatus(BaseModel):
    asset_key: AssetKey
    name: str
    source: str
    source_symbol: str
    row_count: int = 0
    start_date: str = ""
    end_date: str = ""
    is_cached: bool = False
    data_quality: str
    notes: List[str] = Field(default_factory=list)


class HistoricalDataStatus(BaseModel):
    generated_at: datetime
    sources: List[HistoricalDataSourceStatus]
    data_quality: str
    notes: List[str]
    auto_refresh_status: str = "not_checked"
    auto_refresh_message: str = ""
    last_refresh_at: str = ""


class MonthlyPlanRequest(BaseModel):
    profile: Optional[Profile] = None
    cash_pool: Optional[CashPool] = None
    strategy_id: Optional[str] = None
    custom_weights: Optional[Dict[AssetKey, float]] = None


class MonthlyAllocation(BaseModel):
    asset_key: AssetKey
    name: str
    target_weight: float
    amount: float
    temperature: float
    multiplier: float


class MonthlyPlan(BaseModel):
    strategy_id: str
    strategy_name: str
    generated_at: datetime
    average_temperature: float
    temperature_band: str
    base_amount: float
    multiplier: float
    suggested_total_buy: float
    allocations: List[MonthlyAllocation]
    cash_after: CashPool
    risk_notes: List[str]
    rebalance_notes: List[str]
    education_message: str
    data_quality_status: str


class InvestmentRecord(BaseModel):
    id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: str
    plan: MonthlyPlan
    ai_explanation: str = ""
    executed: bool = False
    execution_note: str = ""


class ProviderConfigIn(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    model: str = "deepseek-chat"
    temperature: float = Field(default=0.3, ge=0, le=2)


class ProviderConfigOut(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    api_key_set: bool = False
    api_key_mask: str = ""
    model: str = "deepseek-chat"
    temperature: float = 0.3


class AIExplainRequest(BaseModel):
    plan: MonthlyPlan
    tone: str = "calm_coach"


class AIExplainResponse(BaseModel):
    explanation: str
    provider_used: str
    fallback: bool


class AgentToolTrace(BaseModel):
    name: str
    status: Literal["done", "warning", "blocked"]
    summary: str
    evidence: List[str] = Field(default_factory=list)


class AgentWorkbenchResponse(BaseModel):
    generated_at: datetime
    provider_used: str
    fallback: bool
    headline: str
    brief: str
    tools: List[AgentToolTrace]
    next_actions: List[str]
    missing_data: List[str]
    suggested_questions: List[str]


class AgentChatRequest(BaseModel):
    question: str
    profile: Optional[Profile] = None
    strategy: Optional[StrategyTemplate] = None
    market: Optional[MarketSnapshot] = None
    plan: Optional[MonthlyPlan] = None
    records: List[InvestmentRecord] = Field(default_factory=list)


class AgentChatResponse(BaseModel):
    answer: str
    provider_used: str
    fallback: bool
    tools: List[AgentToolTrace]
    suggested_questions: List[str]


class DisciplineReviewResponse(BaseModel):
    generated_at: datetime
    provider_used: str
    fallback: bool
    score: int = Field(ge=0, le=100)
    summary: str
    observations: List[str]
    next_actions: List[str]
