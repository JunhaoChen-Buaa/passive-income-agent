import type {
  AgentChatResponse,
  AgentWorkbench,
  BacktestResult,
  CashPool,
  DisciplineReview,
  HistoricalDataStatus,
  InvestmentRecord,
  MarketSnapshot,
  MonthlyPlan,
  PersonalStrategyRequest,
  PersonalStrategyResponse,
  Profile,
  ProviderConfigOut,
  StrategyTemplate,
} from './types';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>('/api/health'),
  getProfile: () => request<Profile>('/api/profile'),
  saveProfile: (profile: Profile) =>
    request<Profile>('/api/profile', { method: 'PUT', body: JSON.stringify(profile) }),
  getStrategies: () => request<StrategyTemplate[]>('/api/strategies'),
  getBacktests: () => request<BacktestResult[]>('/api/backtest/default-comparison'),
  runBacktest: (
    strategyId: string,
    initialCapital: number,
    monthlyContribution: number,
    startMonth?: string,
    endMonth?: string,
  ) =>
    request<BacktestResult>('/api/backtest', {
      method: 'POST',
      body: JSON.stringify({
        strategy_id: strategyId,
        initial_capital: initialCapital,
        monthly_contribution: monthlyContribution,
        start_month: startMonth || undefined,
        end_month: endMonth || undefined,
        data_mode: 'history',
      }),
    }),
  getCashPool: () => request<CashPool>('/api/cash-pool'),
  saveCashPool: (cashPool: CashPool) =>
    request<CashPool>('/api/cash-pool', { method: 'PUT', body: JSON.stringify(cashPool) }),
  getMarket: (forceRefresh = false) =>
    request<MarketSnapshot>(`/api/market-snapshot?force_refresh=${forceRefresh ? 'true' : 'false'}`),
  getHistoryDataStatus: () => request<HistoricalDataStatus>('/api/history-data/status'),
  refreshHistoryData: () =>
    request<HistoricalDataStatus>('/api/history-data/refresh', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  autoRefreshHistoryData: () =>
    request<HistoricalDataStatus>('/api/history-data/auto-refresh', {
      method: 'POST',
      body: JSON.stringify({}),
    }),
  getMonthlyPlan: (strategyId: string) =>
    request<MonthlyPlan>('/api/monthly-plan', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId }),
    }),
  generatePersonalStrategy: (payload: PersonalStrategyRequest) =>
    request<PersonalStrategyResponse>('/api/personal-strategy/generate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  explain: (plan: MonthlyPlan) =>
    request<{ explanation: string; provider_used: string; fallback: boolean }>('/api/ai-explain', {
      method: 'POST',
      body: JSON.stringify({ plan }),
    }),
  getAgentWorkbench: (withAi = false) =>
    request<AgentWorkbench>(`/api/agent/workbench?with_ai=${withAi ? 'true' : 'false'}`),
  askAgent: (payload: {
    question: string;
    profile?: Profile;
    strategy?: StrategyTemplate;
    market?: MarketSnapshot | null;
    plan?: MonthlyPlan | null;
    records?: InvestmentRecord[];
  }) =>
    request<AgentChatResponse>('/api/agent/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getRecords: () => request<InvestmentRecord[]>('/api/records'),
  getDisciplineReview: (withAi = false) =>
    request<DisciplineReview>(`/api/records/discipline-review?with_ai=${withAi ? 'true' : 'false'}`),
  createRecord: (record: Omit<InvestmentRecord, 'id'>) =>
    request<{ id: number; duplicate?: boolean }>('/api/records', { method: 'POST', body: JSON.stringify(record) }),
  updateRecord: (id: number, executed: boolean, executionNote: string) =>
    request<{ ok: boolean }>(`/api/records/${id}/execution`, {
      method: 'PUT',
      body: JSON.stringify({ executed, execution_note: executionNote }),
    }),
  getProviderConfig: () => request<ProviderConfigOut>('/api/provider-config'),
  saveProviderConfig: (payload: {
    provider: string;
    base_url: string;
    api_key: string;
    model: string;
    temperature: number;
  }) =>
    request<ProviderConfigOut>('/api/provider-config', {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
};
