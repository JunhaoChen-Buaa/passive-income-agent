export type AssetKey =
  | 'china_large'
  | 'china_mid'
  | 'china_dividend'
  | 'sp500'
  | 'nasdaq100';

export type Profile = {
  lump_sum_capital: number;
  monthly_contribution: number;
  emergency_cash_floor: number;
  current_cash: number;
  risk_preference: 'conservative' | 'balanced' | 'growth';
  investment_months: number;
  selected_strategy_id: string;
  holdings: Record<string, number>;
};

export type StrategyTemplate = {
  id: string;
  name: string;
  level: string;
  positioning: string;
  audience: string;
  return_sources: string[];
  risks: string[];
  weights: Record<AssetKey, number>;
  is_personalized?: boolean;
};

export type PersonalStrategyRequest = {
  profile: Profile;
  goals: string;
  investment_horizon: string;
  drawdown_tolerance: string;
  preferences: string;
  template_hint: string;
};

export type PersonalStrategyResponse = {
  strategy: StrategyTemplate;
  explanation: string;
  provider_used: string;
  fallback: boolean;
  backtest?: BacktestResult | null;
};

export type EquityPoint = {
  date: string;
  value: number;
  nav: number;
};

export type BacktestResult = {
  strategy_id: string;
  strategy_name: string;
  annualized_return: number;
  max_drawdown: number;
  annualized_volatility: number;
  worst_year: string;
  worst_year_return: number;
  longest_recovery_months: number;
  trailing_returns: Record<string, number>;
  final_value: number;
  total_contributed: number;
  equity_curve: EquityPoint[];
  data_quality: string;
  notes: string[];
};

export type CashPool = {
  emergency_cash: number;
  queue_cash: number;
  opportunity_cash: number;
  parking_tool: string;
  notes: string;
};

export type MarketAssetSnapshot = {
  asset_key: AssetKey;
  name: string;
  source: string;
  source_symbol: string;
  as_of: string;
  is_live: boolean;
  price: number;
  temperature: number;
  valuation_percentile?: number | null;
  ma200_position: number;
  drawdown: number;
  volatility: number;
  dividend_yield_percentile?: number | null;
  data_quality: string;
  notes: string[];
};

export type MarketSnapshot = {
  generated_at: string;
  assets: MarketAssetSnapshot[];
  data_quality: string;
  notes: string[];
};

export type HistoricalDataSourceStatus = {
  asset_key: AssetKey;
  name: string;
  source: string;
  source_symbol: string;
  row_count: number;
  start_date: string;
  end_date: string;
  is_cached: boolean;
  data_quality: string;
  notes: string[];
};

export type HistoricalDataStatus = {
  generated_at: string;
  sources: HistoricalDataSourceStatus[];
  data_quality: string;
  notes: string[];
  auto_refresh_status?: string;
  auto_refresh_message?: string;
  last_refresh_at?: string;
};

export type MonthlyAllocation = {
  asset_key: AssetKey;
  name: string;
  target_weight: number;
  amount: number;
  temperature: number;
  multiplier: number;
};

export type MonthlyPlan = {
  strategy_id: string;
  strategy_name: string;
  generated_at: string;
  average_temperature: number;
  temperature_band: string;
  base_amount: number;
  multiplier: number;
  suggested_total_buy: number;
  allocations: MonthlyAllocation[];
  cash_after: CashPool;
  risk_notes: string[];
  rebalance_notes: string[];
  education_message: string;
  data_quality_status: string;
};

export type ProviderConfigOut = {
  provider: string;
  base_url: string;
  api_key_set: boolean;
  api_key_mask: string;
  model: string;
  temperature: number;
};

export type InvestmentRecord = {
  id: number;
  created_at: string;
  strategy_id: string;
  plan: MonthlyPlan;
  ai_explanation: string;
  executed: boolean;
  execution_note: string;
};
