import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  BarChart3,
  BookOpen,
  Brain,
  CalendarCheck,
  CircleDollarSign,
  Database,
  HelpCircle,
  Landmark,
  LineChart,
  ListChecks,
  MessageCircle,
  PiggyBank,
  RefreshCw,
  Save,
  Send,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  WalletCards,
  X,
} from 'lucide-react';
import { api } from './api';
import type {
  AgentChatResponse,
  AgentWorkbench,
  AssetKey,
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
import './styles.css';

const navGroups = [
  {
    title: 'AI流程',
    items: [
      { id: 'home', label: 'AI工作台', icon: Landmark },
      { id: 'tutorial', label: '使用教程', icon: HelpCircle },
      { id: 'advisor', label: '我的策略', icon: Brain },
      { id: 'action', label: '行动指南', icon: CalendarCheck },
    ],
  },
  {
    title: '研究判断',
    items: [
      { id: 'backtest', label: '策略回测', icon: LineChart },
      { id: 'market', label: '每日评估', icon: Activity },
    ],
  },
  {
    title: '资金记录',
    items: [
      { id: 'plan', label: '定投计划', icon: SlidersHorizontal },
      { id: 'cash', label: '现金池', icon: WalletCards },
      { id: 'records', label: '投资记录', icon: ListChecks },
    ],
  },
  {
    title: '学习设置',
    items: [
      { id: 'dividend', label: '红利模块', icon: CircleDollarSign },
      { id: 'education', label: '复利科普', icon: BookOpen },
      { id: 'settings', label: '设置', icon: Settings },
    ],
  },
] as const;

const fmtMoney = (value: number) =>
  new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 }).format(value);
const fmtPct = (value: number) => `${(value * 100).toFixed(1)}%`;
const fmtSignedPct = (value: number) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`;
const dataQualityLabels: Record<string, string> = {
  HISTORICAL_EASTMONEY_ADJUSTED_MONTHLY: '历史行情回测',
  PROXY_FALLBACK_HISTORY_DATA_UNAVAILABLE: '数据不足，已降级',
  MVP_PROXY_ANNUAL_DATA: '代理年度数据',
  HISTORY_CACHE_READY: '历史数据已就绪',
  HISTORY_CACHE_PARTIAL: '部分历史数据',
  HISTORY_CACHE_EMPTY: '待刷新历史数据',
  HISTORY_CACHE_INCOMPLETE: '历史数据不足',
  LIVE_EASTMONEY_PRICE_TECHNICAL_NO_VALUATION: '真实行情，缺估值',
  LIVE_PRICE_TECHNICAL_NO_VALUATION: '真实价格，缺估值',
  PROXY_FALLBACK_LIVE_FETCH_FAILED: '行情获取失败，已降级',
  MVP_PROXY_METRICS: '代理市场指标',
  代理指标: '代理指标',
};
const qualityLabel = (value?: string | null, fallback = '未加载') => (value ? dataQualityLabels[value] || value : fallback);
const planFingerprint = (plan?: MonthlyPlan | null) => {
  if (!plan) return '';
  const allocations = plan.allocations.map((item) => ({
    asset_key: item.asset_key,
    target_weight: Number(item.target_weight.toFixed(6)),
    amount: Number(item.amount.toFixed(2)),
    multiplier: Number(item.multiplier.toFixed(4)),
  }));
  return JSON.stringify({
    strategy_id: plan.strategy_id,
    suggested_total_buy: Number(plan.suggested_total_buy.toFixed(2)),
    base_amount: Number(plan.base_amount.toFixed(2)),
    multiplier: Number(plan.multiplier.toFixed(4)),
    average_temperature: Number(plan.average_temperature.toFixed(2)),
    temperature_band: plan.temperature_band,
    allocations,
  });
};
const multiplierRangeForTemperature = (value: number) => {
  if (value < 25) return '150%-200%';
  if (value < 45) return '120%-150%';
  if (value < 65) return '100%';
  if (value < 80) return '70%';
  return '50%';
};
const assetLabels: Record<AssetKey, string> = {
  china_large: 'A股大盘',
  china_mid: '中证500',
  china_dividend: '红利',
  sp500: '标普500',
  nasdaq100: '纳指100',
};

const defaultProfile: Profile = {
  lump_sum_capital: 100000,
  monthly_contribution: 1000,
  emergency_cash_floor: 30000,
  current_cash: 130000,
  risk_preference: 'balanced',
  investment_months: 12,
  selected_strategy_id: 'balanced_compound',
  holdings: {},
};

const defaultCash: CashPool = {
  emergency_cash: 30000,
  queue_cash: 70000,
  opportunity_cash: 20000,
  parking_tool: '货币基金 / 现金管理 / 银行低风险流动性产品',
  notes: '现金池用于保流动性、等待定投节奏和低温机会；不描述为保本。',
};

type AIStatus = {
  explanationProvider: string;
  explanationFallback: boolean;
  strategyProvider: string;
  strategyFallback: boolean;
  lastAction: string;
};

function App() {
  const [activePage, setActivePage] = useState('home');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [strategies, setStrategies] = useState<StrategyTemplate[]>([]);
  const [profile, setProfile] = useState<Profile>(defaultProfile);
  const [cashPool, setCashPool] = useState<CashPool>(defaultCash);
  const [backtests, setBacktests] = useState<BacktestResult[]>([]);
  const [market, setMarket] = useState<MarketSnapshot | null>(null);
  const [plan, setPlan] = useState<MonthlyPlan | null>(null);
  const [explanation, setExplanation] = useState('');
  const [records, setRecords] = useState<InvestmentRecord[]>([]);
  const [provider, setProvider] = useState<ProviderConfigOut | null>(null);
  const [historyStatus, setHistoryStatus] = useState<HistoricalDataStatus | null>(null);
  const [agentWorkbench, setAgentWorkbench] = useState<AgentWorkbench | null>(null);
  const [disciplineReview, setDisciplineReview] = useState<DisciplineReview | null>(null);
  const [notice, setNotice] = useState('');
  const [marketRefreshing, setMarketRefreshing] = useState(false);
  const [historyRefreshing, setHistoryRefreshing] = useState(false);
  const [aiStatus, setAiStatus] = useState<AIStatus>({
    explanationProvider: '未运行',
    explanationFallback: true,
    strategyProvider: '未生成',
    strategyFallback: true,
    lastAction: '等待生成计划',
  });

  const selectedStrategy = useMemo(
    () => strategies.find((item) => item.id === profile.selected_strategy_id) || strategies[0],
    [strategies, profile.selected_strategy_id],
  );
  const selectedBacktest = useMemo(
    () => backtests.find((item) => item.strategy_id === profile.selected_strategy_id) || backtests[0],
    [backtests, profile.selected_strategy_id],
  );
  const savedPersonalStrategy = useMemo(
    () => strategies.find((item) => item.is_personalized),
    [strategies],
  );
  const personalBacktest = useMemo(
    () => (savedPersonalStrategy ? backtests.find((item) => item.strategy_id === savedPersonalStrategy.id) : undefined),
    [backtests, savedPersonalStrategy],
  );
  const currentPlanSaved = useMemo(
    () => Boolean(plan && records.some((record) => planFingerprint(record.plan) === planFingerprint(plan))),
    [records, plan],
  );

  async function refreshAll() {
    setLoading(true);
    setError('');
    try {
      const [strategyData, profileData, cashData, comparison, marketData, recordData, providerData, historyData] =
        await Promise.all([
          api.getStrategies(),
          api.getProfile(),
          api.getCashPool(),
          api.getBacktests(),
          api.getMarket(),
          api.getRecords(),
          api.getProviderConfig(),
          api.getHistoryDataStatus(),
        ]);
      setStrategies(strategyData);
      setProfile(profileData);
      setCashPool(cashData);
      setBacktests(comparison);
      setMarket(marketData);
      setRecords(recordData);
      setProvider(providerData);
      setHistoryStatus(historyData);
      const autoHistoryData = await api.autoRefreshHistoryData();
      setHistoryStatus(autoHistoryData);
      if (autoHistoryData.auto_refresh_status?.includes('refreshed') || autoHistoryData.auto_refresh_status?.includes('partial')) {
        setBacktests(await api.getBacktests());
      }
      if (autoHistoryData.auto_refresh_status === 'auto_refreshed') {
        setNotice(autoHistoryData.auto_refresh_message || '历史行情已自动刷新。');
      }
      const planData = await api.getMonthlyPlan(profileData.selected_strategy_id);
      setPlan(planData);
      setLoading(false);
      refreshAgentWorkbench(false).catch((err) => {
        setError(err instanceof Error ? err.message : 'AI 工作台刷新失败');
      });
      const ai = await api.explain(planData);
      setExplanation(ai.explanation);
      setAiStatus((current) => ({
        ...current,
        explanationProvider: ai.provider_used,
        explanationFallback: ai.fallback,
        lastAction: ai.fallback ? '本地规则已解释本月计划' : 'DeepSeek 已解释本月计划',
      }));
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshAll();
  }, []);

  async function refreshAgentWorkbench(withAi = false) {
    const [workbenchData, reviewData] = await Promise.all([
      api.getAgentWorkbench(withAi),
      api.getDisciplineReview(withAi),
    ]);
    setAgentWorkbench(workbenchData);
    setDisciplineReview(reviewData);
    return workbenchData;
  }

  async function runAgentSynthesis() {
    setError('');
    setNotice(provider?.api_key_set ? 'AI 正在综合当前策略、市场、计划和记录。' : '未配置 API Key，将使用本地 Agent 工作台。');
    try {
      const workbench = await refreshAgentWorkbench(Boolean(provider?.api_key_set));
      setAiStatus((current) => ({
        ...current,
        lastAction: workbench.fallback ? '本地 Agent 已完成工作台综合' : `${workbench.provider_used} 已完成工作台综合`,
      }));
      setNotice(workbench.fallback ? '本地 Agent 工作台已刷新。' : 'AI 已综合当前上下文，工作台已刷新。');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI 工作台刷新失败');
    }
  }

  async function selectStrategy(strategyId: string) {
    const updated = { ...profile, selected_strategy_id: strategyId };
    setProfile(updated);
    setNotice('');
    try {
      await api.saveProfile(updated);
      const [comparison, planData] = await Promise.all([
        api.getBacktests(),
        api.getMonthlyPlan(strategyId),
      ]);
      setBacktests(comparison);
      setPlan(planData);
      const ai = await api.explain(planData);
      setExplanation(ai.explanation);
      setAiStatus((current) => ({
        ...current,
        explanationProvider: ai.provider_used,
        explanationFallback: ai.fallback,
        lastAction: ai.fallback ? '本地规则已解释切换后的计划' : 'DeepSeek 已解释切换后的计划',
      }));
      await refreshAgentWorkbench(false);
      setNotice('策略已切换，本月计划已重新计算。');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存策略失败');
    }
  }

  async function saveProfileAndPlan(nextProfile = profile, nextCash = cashPool) {
    setError('');
    try {
      await api.saveProfile(nextProfile);
      await api.saveCashPool(nextCash);
      const [comparison, planData] = await Promise.all([
        api.getBacktests(),
        api.getMonthlyPlan(nextProfile.selected_strategy_id),
      ]);
      setBacktests(comparison);
      setPlan(planData);
      const ai = await api.explain(planData);
      setExplanation(ai.explanation);
      setAiStatus((current) => ({
        ...current,
        explanationProvider: ai.provider_used,
        explanationFallback: ai.fallback,
        lastAction: ai.fallback ? '本地规则已解释保存后的计划' : 'DeepSeek 已解释保存后的计划',
      }));
      await refreshAgentWorkbench(false);
      setNotice('配置已保存，计划已刷新。');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    }
  }

  async function refreshMarket(forceRefresh = true) {
    setError('');
    setMarketRefreshing(true);
    try {
      const marketData = await api.getMarket(forceRefresh);
      setMarket(marketData);
      const planData = await api.getMonthlyPlan(profile.selected_strategy_id);
      setPlan(planData);
      const ai = await api.explain(planData);
      setExplanation(ai.explanation);
      setAiStatus((current) => ({
        ...current,
        explanationProvider: ai.provider_used,
        explanationFallback: ai.fallback,
        lastAction: ai.fallback ? '市场已刷新，本地规则已解释' : '市场已刷新，DeepSeek 已解释',
      }));
      await refreshAgentWorkbench(false);
      setNotice(`每日指数评估已刷新：${qualityLabel(marketData.data_quality)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '刷新市场数据失败');
    } finally {
      setMarketRefreshing(false);
    }
  }

  async function refreshHistoryData() {
    setError('');
    setNotice('');
    setHistoryRefreshing(true);
    try {
      const status = await api.refreshHistoryData();
      setHistoryStatus(status);
      const comparison = await api.getBacktests();
      setBacktests(comparison);
      await refreshAgentWorkbench(false);
      const ready = status.sources.filter((source) => source.data_quality === 'HISTORY_CACHE_READY').length;
      setNotice(`历史行情工具已刷新：${ready}/${status.sources.length} 类资产可用于历史回测。`);
    } catch (err) {
      setError(err instanceof Error ? err.message : '刷新历史行情失败');
    } finally {
      setHistoryRefreshing(false);
    }
  }

  async function generatePersonalStrategy(payload: PersonalStrategyRequest): Promise<PersonalStrategyResponse> {
    setError('');
    setNotice('');
    const response = await api.generatePersonalStrategy(payload);
    const updatedProfile = { ...payload.profile, selected_strategy_id: response.strategy.id };
    setProfile(updatedProfile);
    setAiStatus((current) => ({
      ...current,
      strategyProvider: response.provider_used,
      strategyFallback: response.fallback,
      lastAction: response.fallback ? '已生成本地个人策略草案' : 'DeepSeek 已生成个人策略草案',
    }));

    const [strategyData, comparison, planData, historyData] = await Promise.all([
      api.getStrategies(),
      api.getBacktests(),
      api.getMonthlyPlan(response.strategy.id),
      api.getHistoryDataStatus(),
    ]);
    setStrategies(strategyData);
    setBacktests(comparison);
    setPlan(planData);
    setHistoryStatus(historyData);
    const ai = await api.explain(planData);
    setExplanation(ai.explanation);
    setAiStatus((current) => ({
      ...current,
      explanationProvider: ai.provider_used,
      explanationFallback: ai.fallback,
      lastAction: response.fallback
        ? '本地个人策略已保存，纪律计划已生成'
        : 'DeepSeek 个人策略已保存，纪律计划已生成',
    }));
    await refreshAgentWorkbench(false);
    setNotice(
      response.fallback
        ? `已保存到「我的策略」，并已生成个人回测：${response.backtest ? qualityLabel(response.backtest.data_quality) : '等待回测'}。`
        : `DeepSeek 已生成并保存到「我的策略」，个人回测已生成：${response.backtest ? qualityLabel(response.backtest.data_quality) : '等待回测'}。`,
    );
    return response;
  }

  async function saveRecord() {
    if (!plan) return;
    if (currentPlanSaved) {
      setNotice('这条建议已经在投资记录里，不需要重复保存。');
      setActivePage('records');
      return;
    }
    try {
      const created = await api.createRecord({
        created_at: new Date().toISOString(),
        strategy_id: plan.strategy_id,
        plan,
        ai_explanation: explanation,
        executed: false,
        execution_note: '',
      });
      const recordData = await api.getRecords();
      setRecords(recordData);
      await refreshAgentWorkbench(false);
      setNotice(created.duplicate ? '这条建议之前已经保存过，已为你打开投资记录。' : '本次建议已保存到投资记录。');
      setActivePage('records');
    } catch (err) {
      setError(err instanceof Error ? err.message : '记录保存失败');
    }
  }

  async function markRecord(record: InvestmentRecord, executed: boolean) {
    try {
      setRecords((current) =>
        current.map((item) => (item.id === record.id ? { ...item, executed } : item)),
      );
      await api.updateRecord(record.id, executed, record.execution_note || '');
      const recordData = await api.getRecords();
      setRecords(recordData);
      await refreshAgentWorkbench(false);
      setNotice(executed ? '已标记为已执行。' : '已标记为待执行。');
    } catch (err) {
      setRecords(await api.getRecords());
      setError(err instanceof Error ? err.message : '更新记录失败');
    }
  }

  const page = (() => {
    if (activePage === 'home') {
      return (
        <HomePage
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          selectedBacktest={selectedBacktest}
          backtests={backtests}
          profile={profile}
          cashPool={cashPool}
          market={market}
          provider={provider}
          aiStatus={aiStatus}
          agentWorkbench={agentWorkbench}
          plan={plan}
          explanation={explanation}
          currentPlanSaved={currentPlanSaved}
          onSelectStrategy={selectStrategy}
          onSaveRecord={saveRecord}
          onGoTutorial={() => setActivePage('tutorial')}
          onGoAdvisor={() => setActivePage('advisor')}
          onGoMarket={() => setActivePage('market')}
          onGoAction={() => setActivePage('action')}
          onRefreshMarket={() => refreshMarket(true)}
          onRunAgent={runAgentSynthesis}
          marketRefreshing={marketRefreshing}
        />
      );
    }
    if (activePage === 'advisor') {
      return (
        <AdvisorPage
          profile={profile}
          strategies={strategies}
          selectedStrategy={selectedStrategy}
          savedPersonalStrategy={savedPersonalStrategy}
          personalBacktest={personalBacktest}
          provider={provider}
          onGenerate={generatePersonalStrategy}
          onGoAction={() => setActivePage('action')}
          onGoBacktest={() => setActivePage('backtest')}
          onGoHome={() => setActivePage('home')}
        />
      );
    }
    if (activePage === 'tutorial') {
      return <TutorialPage onGoAdvisor={() => setActivePage('advisor')} onGoBacktest={() => setActivePage('backtest')} onGoAction={() => setActivePage('action')} />;
    }
    if (activePage === 'backtest') {
      return (
        <BacktestPage
          strategies={strategies}
          backtests={backtests}
          profile={profile}
          selectedId={profile.selected_strategy_id}
          historyStatus={historyStatus}
          historyRefreshing={historyRefreshing}
          onSelectStrategy={selectStrategy}
          onRefreshHistory={refreshHistoryData}
        />
      );
    }
    if (activePage === 'action') {
      return (
        <ActionGuidePage
          profile={profile}
          market={market}
          plan={plan}
          selectedStrategy={selectedStrategy}
          onRefresh={() => refreshMarket(true)}
          refreshing={marketRefreshing}
        />
      );
    }
    if (activePage === 'plan') {
      return <PlanPage profile={profile} setProfile={setProfile} cashPool={cashPool} setCashPool={setCashPool} strategies={strategies} onSave={saveProfileAndPlan} plan={plan} />;
    }
    if (activePage === 'market') {
      return <MarketPage market={market} plan={plan} onRefresh={() => refreshMarket(true)} refreshing={marketRefreshing} />;
    }
    if (activePage === 'cash') {
      return <CashPage profile={profile} setProfile={setProfile} cashPool={cashPool} setCashPool={setCashPool} onSave={saveProfileAndPlan} />;
    }
    if (activePage === 'dividend') {
      return <DividendPage />;
    }
    if (activePage === 'education') {
      return <EducationPage />;
    }
    if (activePage === 'records') {
      return <RecordsPage records={records} review={disciplineReview} onMark={markRecord} onRefreshReview={runAgentSynthesis} />;
    }
    return <SettingsPage provider={provider} onSaved={async () => setProvider(await api.getProviderConfig())} />;
  })();

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><PiggyBank size={23} /></div>
          <div>
            <strong>指数基金 Agent</strong>
            <span>长期纪律工具</span>
          </div>
        </div>
        <nav className="nav-list" aria-label="主导航">
          {navGroups.map((group) => (
            <div className="nav-group" key={group.title}>
              <span className="nav-group-title">{group.title}</span>
              {group.items.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={activePage === item.id ? 'nav-item active' : 'nav-item'}
                    onClick={() => setActivePage(item.id)}
                    title={item.label}
                  >
                    <Icon size={18} />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={17} />
          <span>规则先行，AI 只解释，不下单。</span>
        </div>
      </aside>
      <main className="main">
        {error && <div className="banner danger">{error}</div>}
        {notice && <div className="banner success">{notice}</div>}
        {loading ? <LoadingState /> : page}
      </main>
      <ProductAskBubble
        profile={profile}
        strategy={selectedStrategy}
        market={market}
        plan={plan}
        records={records}
        suggestedQuestions={agentWorkbench?.suggested_questions || []}
      />
    </div>
  );
}

type AskMessage = {
  role: 'user' | 'assistant';
  text: string;
};

function answerProductQuestion(question: string) {
  const text = question.toLowerCase();
  if (text.includes('回测') || text.includes('历史') || text.includes('收益')) {
    return '回测优先使用本地历史行情工具：东方财富日K线会缓存到本地 SQLite，再聚合为月度收益。若页面显示“历史行情回测”，说明不是演示数据；若显示“数据不足，已降级”，就只能作为认知辅助。';
  }
  if (text.includes('个人') || text.includes('策略')) {
    return '个人策略会保存在“我的策略”页顶部，并自动成为首页、行动指南和策略回测使用的当前策略。生成后页面会同步展示“个人策略历史回测”，也可以点“查看完整个人回测”。';
  }
  if (text.includes('现金') || text.includes('货币') || text.includes('没投')) {
    return '还没投进去的钱会进入现金池：应急现金不投资，排队资金按6-18个月逐步买入，机会资金只在市场很冷时提前动用。默认停放方向是货币基金、现金管理或银行低风险流动性产品，但都不描述为保本。';
  }
  if (text.includes('deepseek') || text.includes('ai') || text.includes('模型')) {
    return 'DeepSeek 在这里是解释器和策略草案助手，不直接决定买卖金额。具体买入金额由规则引擎根据策略权重、现金池和市场温度生成。';
  }
  if (text.includes('执行') || text.includes('记录') || text.includes('保存')) {
    return '投资记录用于保存每次建议和执行状态。同一条建议保存过后会显示“本次建议已保存”，不会重复插入；执行后可以在投资记录里标记“已执行”或改回“待执行”。';
  }
  if (text.includes('风险') || text.includes('亏') || text.includes('下跌')) {
    return '指数基金仍然是权益资产，会有回撤。产品不会承诺收益，也不自动下单；它做的是把长期配置、现金纪律、市场温度和执行记录放到一个流程里，帮助你少做情绪化动作。';
  }
  return '你可以问我：个人策略保存在哪、回测数据是否真实、现金池怎么放、DeepSeek 起什么作用、投资记录怎么用。这个问一问目前是产品规则助手，后续可以接入 DeepSeek 做更自由的对话。';
}

function ProductAskBubble({
  profile,
  strategy,
  market,
  plan,
  records,
  suggestedQuestions,
}: {
  profile: Profile;
  strategy?: StrategyTemplate;
  market: MarketSnapshot | null;
  plan: MonthlyPlan | null;
  records: InvestmentRecord[];
  suggestedQuestions: string[];
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [asking, setAsking] = useState(false);
  const [messages, setMessages] = useState<AskMessage[]>([
    { role: 'assistant', text: '你好，我会读取你的策略、市场温度、行动计划和投资记录来回答。金额仍以规则引擎为准。' },
  ]);

  async function submitQuestion(questionOverride?: string) {
    const question = (questionOverride || input).trim();
    if (!question) return;
    setMessages((current) => [...current, { role: 'user', text: question }]);
    setInput('');
    setAsking(true);
    try {
      const response: AgentChatResponse = await api.askAgent({
        question,
        profile,
        strategy,
        market,
        plan,
        records,
      });
      const trace = response.tools?.[0]?.summary ? `\n\n已调用：${response.tools.map((tool) => tool.name).join('、')}` : '';
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: `${response.answer}${trace}` },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        { role: 'assistant', text: answerProductQuestion(question) },
      ]);
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className={open ? 'ask-bubble open' : 'ask-bubble'}>
      {open && (
        <section className="ask-panel" aria-label="产品问一问">
          <div className="ask-head">
            <div>
              <strong>问一问</strong>
              <span>上下文 Agent</span>
            </div>
            <button type="button" onClick={() => setOpen(false)} title="关闭问一问">
              <X size={18} />
            </button>
          </div>
          <div className="ask-messages">
            {messages.map((message, index) => (
              <div className={message.role === 'user' ? 'ask-message user' : 'ask-message'} key={`${message.role}-${index}`}>
                {message.text}
              </div>
            ))}
            {asking && <div className="ask-message">正在读取当前上下文...</div>}
          </div>
          {suggestedQuestions.length > 0 && (
            <div className="ask-suggestions">
              {suggestedQuestions.slice(0, 3).map((question) => (
                <button type="button" key={question} onClick={() => submitQuestion(question)}>
                  {question}
                </button>
              ))}
            </div>
          )}
          <div className="ask-input">
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') submitQuestion();
              }}
              placeholder="问你的策略、行动、市场..."
            />
            <button type="button" onClick={() => submitQuestion()} disabled={asking} title="发送问题">
              <Send size={17} />
            </button>
          </div>
        </section>
      )}
      <button className="ask-trigger" type="button" onClick={() => setOpen((value) => !value)} title="打开问一问">
        <MessageCircle size={22} />
        <span className="ask-trigger-label">问一问</span>
      </button>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-panel">
      <Database size={28} />
      <strong>正在加载本地策略引擎</strong>
      <span>策略、现金池、回测和月度建议正在汇总。</span>
    </div>
  );
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <header className="page-header">
      <span className="eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </header>
  );
}

function TutorialPage({ onGoAdvisor, onGoBacktest, onGoAction }: {
  onGoAdvisor: () => void;
  onGoBacktest: () => void;
  onGoAction: () => void;
}) {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="使用教程"
        title="这个 Agent 解决的是普通人长期指数投资的执行问题。"
        description="它不是预测神器，也不是自动下单工具。它把策略选择、历史回测、现金池、市场温度、月度行动和投资记录放进一个有纪律的流程里。"
      />
      <section className="panel tutorial-hero">
        <h2>背景：普通人真正难的不是知道要长期投资，而是能不能长期执行。</h2>
        <p className="lead">
          指数基金投资的核心并不复杂：低成本、分散、长期、定期投入。难点在于市场涨跌会不断干扰人，
          手里有钱时不知道怎么分批，跌的时候不敢买，涨的时候又容易追高。这个 Agent 的目标，是把这些决策拆成规则和记录。
        </p>
      </section>

      <section className="tutorial-grid">
        <div className="panel">
          <h2>它帮你解决什么</h2>
          <div className="principles">
            <div><strong>选策略</strong><span>先从稳健红利、均衡复利、美股核心、科技成长、A股修复等模板理解风险收益。</span></div>
            <div><strong>定个人方案</strong><span>根据你的资金、现金流、风险偏好和周期，生成一份个人指数配置。</span></div>
            <div><strong>看历史压力</strong><span>用历史行情回测这份配置曾经的年化、回撤、波动和回本时间。</span></div>
            <div><strong>按月执行</strong><span>结合市场温度给出本月买入倍率和金额拆分，帮助你少做情绪化动作。</span></div>
          </div>
        </div>
        <div className="panel warning-panel">
          <h2>它不做什么</h2>
          <ul className="note-list">
            <li>不承诺收益，不保证指数基金只涨不跌。</li>
            <li>不推荐个股，不推荐主动基金，不接券商，不自动下单。</li>
            <li>DeepSeek 或其他模型只解释规则结果，不直接决定买卖金额。</li>
            <li>回测是历史压力测试，不代表未来收益。</li>
          </ul>
        </div>
      </section>

      <section className="panel">
        <h2>推荐使用流程</h2>
        <div className="tutorial-steps">
          <div><strong>1</strong><span>先看首页策略模板，理解不同配置的收益来源和主要风险。</span></div>
          <div><strong>2</strong><span>进入“我的策略”，填写资金、现金流、风险偏好，让 AI 或本地规则生成个人策略。</span></div>
          <div><strong>3</strong><span>查看个人策略历史回测，确认你是否能接受最大回撤、波动和最长回本时间。</span></div>
          <div><strong>4</strong><span>进入“现金池”，把应急现金、定投排队资金、机会资金分清楚。</span></div>
          <div><strong>5</strong><span>每月看“行动指南”，按市场温度决定正常买、少买、暂停或低温多买。</span></div>
          <div><strong>6</strong><span>执行后保存到“投资记录”，标记是否执行，用记录抵抗临时情绪。</span></div>
        </div>
        <div className="action-row">
          <button className="primary-action" onClick={onGoAdvisor} title="开始生成个人策略">
            <Brain size={18} />
            <span>开始生成个人策略</span>
          </button>
          <button className="secondary-action" onClick={onGoBacktest} title="查看策略回测">
            <LineChart size={18} />
            <span>查看策略回测</span>
          </button>
          <button className="secondary-action" onClick={onGoAction} title="查看近期行动指南">
            <CalendarCheck size={18} />
            <span>查看行动指南</span>
          </button>
        </div>
      </section>

      <section className="tutorial-grid">
        <div className="panel">
          <h2>页面怎么用</h2>
          <div className="principles">
            <div><strong>首页</strong><span>看策略模板、本月建议、市场状态和现金池摘要。</span></div>
            <div><strong>我的策略</strong><span>生成并保存你的个人策略，同时查看个人策略回测摘要。</span></div>
            <div><strong>策略回测</strong><span>比较模板和个人策略的历史收益、回撤和净值曲线。</span></div>
            <div><strong>每日评估</strong><span>查看各指数的市场温度、价格趋势、回撤和数据质量。</span></div>
            <div><strong>现金池</strong><span>安排还没买进去的钱，避免一次性情绪化投入。</span></div>
            <div><strong>投资记录</strong><span>保存每次建议和执行状态，方便以后复盘纪律。</span></div>
          </div>
        </div>
        <div className="panel">
          <h2>第一次使用建议</h2>
          <ul className="note-list">
            <li>先不要急着看买入金额，先确认你能接受策略的历史最大回撤。</li>
            <li>先设置应急现金底线，再决定有多少钱可以进入定投排队资金。</li>
            <li>如果还不确定风险偏好，优先从“均衡复利型”或“稳健红利型”开始比较。</li>
            <li>每次执行后都标记记录，产品才会逐渐变成你的纪律账本。</li>
          </ul>
        </div>
      </section>
    </div>
  );
}

function HomePage({
  strategies,
  selectedStrategy,
  selectedBacktest,
  backtests,
  profile,
  cashPool,
  market,
  provider,
  aiStatus,
  agentWorkbench,
  plan,
  explanation,
  currentPlanSaved,
  onSelectStrategy,
  onSaveRecord,
  onGoTutorial,
  onGoAdvisor,
  onGoMarket,
  onGoAction,
  onRefreshMarket,
  onRunAgent,
  marketRefreshing,
}: {
  strategies: StrategyTemplate[];
  selectedStrategy?: StrategyTemplate;
  selectedBacktest?: BacktestResult;
  backtests: BacktestResult[];
  profile: Profile;
  cashPool: CashPool;
  market: MarketSnapshot | null;
  provider: ProviderConfigOut | null;
  aiStatus: AIStatus;
  agentWorkbench: AgentWorkbench | null;
  plan: MonthlyPlan | null;
  explanation: string;
  currentPlanSaved: boolean;
  onSelectStrategy: (id: string) => void;
  onSaveRecord: () => void;
  onGoTutorial: () => void;
  onGoAdvisor: () => void;
  onGoMarket: () => void;
  onGoAction: () => void;
  onRefreshMarket: () => void;
  onRunAgent: () => void;
  marketRefreshing: boolean;
}) {
  const liveAssets = market?.assets.filter((asset) => asset.is_live).length || 0;
  const marketAsOf = market?.assets.find((asset) => asset.as_of)?.as_of || '-';
  return (
    <div className="page-stack">
      <section className="intro-band">
        <div className="intro-copy">
          <span className="eyebrow">AI 先理解你，再调用工具</span>
          <h1>让 Agent 生成个人纪律书，再按每日指数评估执行定投计划。</h1>
          <p>
            AI 不负责拍脑袋买卖，而是读取你的资金、风险偏好、现金池、市场温度、回测和投资记录，
            再调用规则引擎给出可执行纪律。金额由规则生成，AI 负责追问、解释、复盘和发现偏离。
          </p>
          <div className="action-row">
            <button className="secondary-action" onClick={onGoTutorial} title="先了解这个 Agent 解决什么问题和怎么使用">
              <HelpCircle size={18} />
              <span>先看使用教程</span>
            </button>
            <button className="primary-action" onClick={onGoAdvisor} title="进入 AI 策略顾问">
              <Brain size={18} />
              <span>生成个人策略</span>
            </button>
            <button className="secondary-action" onClick={onGoMarket} title="查看每日指数评估">
              <Activity size={18} />
              <span>查看每日评估</span>
            </button>
          </div>
        </div>
        <div className="intro-metrics">
          <Metric label="当前策略" value={selectedStrategy?.name || '-'} sub={selectedStrategy?.is_personalized ? '个人策略' : '模板策略'} />
          <Metric label="本月建议买入" value={`¥${fmtMoney(plan?.suggested_total_buy || 0)}`} />
          <Metric label="组合温度" value={`${plan?.average_temperature || 0}`} sub={plan?.temperature_band || '-'} />
          <Metric label="今日市场数据" value={liveAssets ? `${liveAssets}/5 真实K线` : '代理数据'} sub={marketAsOf} />
        </div>
      </section>

      <AgentWorkbenchPanel
        workbench={agentWorkbench}
        provider={provider}
        onRunAgent={onRunAgent}
        onGoAdvisor={onGoAdvisor}
        onGoAction={onGoAction}
      />

      <section className="workflow-grid">
        <div className="panel workflow-card">
          <BarChart3 size={20} />
          <h2>1. 策略研究室</h2>
          <p>先比较 5 个模板的历史年化、最大回撤、波动和最长回本时间，理解自己在买什么类型的长期配置。</p>
        </div>
        <div className="panel workflow-card">
          <Brain size={20} />
          <h2>2. AI 个人策略</h2>
          <p>填写资金、目标和风险承受度，让 DeepSeek 生成个人配置草案；后端会标准化权重并保存。</p>
        </div>
        <div className="panel workflow-card">
          <Activity size={20} />
          <h2>3. 每日指数评估</h2>
          <p>每天刷新各指数真实K线温度；月度买入金额由现金池、温度和策略权重共同决定。</p>
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <div>
            <h2>策略研究室 · 模板回测</h2>
            <p>这里看的是不同长期配置的历史收益和风险，不是本月个性化买入建议。</p>
          </div>
          <button className="secondary-action" onClick={onGoAdvisor} title="根据你的资料生成个人策略">
            <Brain size={18} />
            <span>生成个人策略</span>
          </button>
        </div>
        <div className="strategy-grid">
          {strategies.map((strategy) => {
            const backtest = backtests.find((item) => item.strategy_id === strategy.id);
            const selected = selectedStrategy?.id === strategy.id;
            return (
              <button
                key={strategy.id}
                className={selected ? 'strategy-card selected' : 'strategy-card'}
                onClick={() => onSelectStrategy(strategy.id)}
              >
                <div className="card-row">
                  <span className="pill">{strategy.is_personalized ? '个人策略' : strategy.level}</span>
                  <span className="data-tag" title={qualityLabel(backtest?.data_quality, '等待回测')}>{qualityLabel(backtest?.data_quality, '等待回测')}</span>
                </div>
                <h3>{strategy.name}</h3>
                <p>{strategy.positioning}</p>
                <div className="mini-metrics">
                  <span>年化 {fmtPct(backtest?.annualized_return || 0)}</span>
                  <span>回撤 {fmtPct(backtest?.max_drawdown || 0)}</span>
                </div>
                <WeightBars weights={strategy.weights} />
              </button>
            );
          })}
        </div>
      </section>

      <section className="section">
        <div className="section-title">
          <div>
            <h2>纪律执行台</h2>
            <p>本月行动建议是个性化执行层：当前策略 + 今日指数评估 + 现金池边界。</p>
          </div>
          <div className="action-row">
            <button className="secondary-action" onClick={onGoAction} title="查看近期行动指南">
              <CalendarCheck size={18} />
              <span>近期行动指南</span>
            </button>
            <button className="secondary-action" onClick={onRefreshMarket} disabled={marketRefreshing} title="刷新真实市场数据并重算计划">
              <RefreshCw size={18} />
              <span>{marketRefreshing ? '刷新中' : '刷新今日评估'}</span>
            </button>
          </div>
        </div>
      </section>

      <section className="dashboard-grid">
        <PlanSummary plan={plan} explanation={explanation} onSaveRecord={onSaveRecord} saved={currentPlanSaved} />
        <TrustPanel
          market={market}
          provider={provider}
          selectedStrategy={selectedStrategy}
          aiStatus={aiStatus}
        />
        <div className="panel">
          <h2>策略回测摘要</h2>
          {selectedBacktest && (
            <>
              <div className="metric-grid">
                <Metric label="年化收益" value={fmtPct(selectedBacktest.annualized_return)} />
                <Metric label="最大回撤" value={fmtPct(selectedBacktest.max_drawdown)} />
                <Metric label="年化波动" value={fmtPct(selectedBacktest.annualized_volatility)} />
                <Metric label="最长回本" value={`${selectedBacktest.longest_recovery_months} 月`} />
              </div>
              <EquityCurve points={selectedBacktest.equity_curve} />
              <p className="fine-print">回测优先使用本地历史行情工具；如显示代理或降级标签，只能作为认知辅助，不能当作准确历史收益。</p>
            </>
          )}
        </div>
        <div className="panel">
          <h2>现金池</h2>
          <CashSplit cashPool={cashPool} />
          <p className="fine-print">未投入资金默认停放在高流动性、低波动工具；货币基金不是存款，也不承诺保本。</p>
        </div>
        <div className="panel">
          <h2>当前输入</h2>
          <div className="key-list">
            <span>一次性待投资金 <strong>¥{fmtMoney(profile.lump_sum_capital)}</strong></span>
            <span>每月新增现金流 <strong>¥{fmtMoney(profile.monthly_contribution)}</strong></span>
            <span>应急现金底线 <strong>¥{fmtMoney(profile.emergency_cash_floor)}</strong></span>
            <span>计划投完时间 <strong>{profile.investment_months} 个月</strong></span>
          </div>
        </div>
      </section>
    </div>
  );
}

function AgentWorkbenchPanel({
  workbench,
  provider,
  onRunAgent,
  onGoAdvisor,
  onGoAction,
}: {
  workbench: AgentWorkbench | null;
  provider: ProviderConfigOut | null;
  onRunAgent: () => void;
  onGoAdvisor: () => void;
  onGoAction: () => void;
}) {
  const tools = workbench?.tools || [];
  return (
    <section className="panel agent-workbench">
      <div className="agent-hero-row">
        <div>
          <span className="eyebrow">AI Agent 工作台</span>
          <h2>{workbench?.headline || '等待 Agent 读取当前上下文'}</h2>
          <p>
            {workbench?.brief ||
              '工作台会读取用户画像、当前策略、每日市场、月度计划、历史数据和投资记录，再给出下一步。'}
          </p>
        </div>
        <div className="agent-controls">
          <span className="pill">{workbench?.fallback ? '本地 Agent' : workbench?.provider_used || '待运行'}</span>
          <button className="primary-action" onClick={onRunAgent} title="让 Agent 重新综合当前上下文">
            <Brain size={18} />
            <span>{provider?.api_key_set ? '让 AI 综合一次' : '刷新本地 Agent'}</span>
          </button>
        </div>
      </div>
      <div className="agent-tool-grid">
        {tools.map((tool) => (
          <div className={`agent-tool-card ${tool.status}`} key={tool.name}>
            <div className="card-row">
              <strong>{tool.name}</strong>
              <span className="pill">{tool.status === 'done' ? '已完成' : tool.status === 'warning' ? '需注意' : '受阻'}</span>
            </div>
            <p>{tool.summary}</p>
            {tool.evidence.length > 0 && (
              <ul>
                {tool.evidence.slice(0, 2).map((item) => <li key={item}>{item}</li>)}
              </ul>
            )}
          </div>
        ))}
        {!tools.length && (
          <div className="agent-tool-card warning">
            <strong>等待运行</strong>
            <p>刷新后会展示 Agent 实际读取和调用的工具。</p>
          </div>
        )}
      </div>
      <div className="agent-bottom-grid">
        <div>
          <h3>下一步</h3>
          <ul className="note-list">
            {(workbench?.next_actions || ['生成个人策略', '查看行动指南', '执行后保存记录']).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h3>数据缺口</h3>
          <ul className="note-list">
            {(workbench?.missing_data?.length ? workbench.missing_data : ['暂无关键阻塞；仍需记住历史数据不代表未来收益。']).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="agent-shortcuts">
          <button className="secondary-action" onClick={onGoAdvisor} title="生成或查看个人策略">
            <Brain size={18} />
            <span>个人策略</span>
          </button>
          <button className="secondary-action" onClick={onGoAction} title="查看近期行动指南">
            <CalendarCheck size={18} />
            <span>行动指南</span>
          </button>
        </div>
      </div>
    </section>
  );
}

function TrustPanel({
  market,
  provider,
  selectedStrategy,
  aiStatus,
}: {
  market: MarketSnapshot | null;
  provider: ProviderConfigOut | null;
  selectedStrategy?: StrategyTemplate;
  aiStatus: AIStatus;
}) {
  const liveAssets = market?.assets.filter((asset) => asset.is_live).length || 0;
  return (
    <div className="panel trust-panel">
      <h2>可信度状态</h2>
      <div className="trust-list">
        <StatusLine
          label="市场数据"
          value={qualityLabel(market?.data_quality)}
          detail={liveAssets ? `${liveAssets}/5 个指数使用真实K线` : '当前使用代理或兜底数据'}
          good={liveAssets > 0}
        />
        <StatusLine
          label="AI解释"
          value={aiStatus.explanationProvider}
          detail={aiStatus.explanationFallback ? '本地规则兜底解释' : 'DeepSeek 已返回解释'}
          good={!aiStatus.explanationFallback}
        />
        <StatusLine
          label="策略来源"
          value={selectedStrategy?.name || '-'}
          detail={selectedStrategy?.is_personalized ? '个人策略已保存' : '当前是模板策略'}
          good={Boolean(selectedStrategy?.is_personalized)}
        />
        <StatusLine
          label="API Key"
          value={provider?.api_key_set ? provider.api_key_mask : '未设置'}
          detail={provider?.api_key_set ? `${provider.provider} / ${provider.model}` : '未设置时仍可用本地规则运行'}
          good={Boolean(provider?.api_key_set)}
        />
      </div>
      <p className="fine-print">最后动作：{aiStatus.lastAction}</p>
    </div>
  );
}

function StatusLine({ label, value, detail, good }: { label: string; value: string; detail: string; good: boolean }) {
  return (
    <div className="status-line">
      <span className={good ? 'status-dot good' : 'status-dot'} />
      <div>
        <strong>{label}</strong>
        <p>{value}</p>
        <em>{detail}</em>
      </div>
    </div>
  );
}

function AdvisorPage({
  profile,
  strategies,
  selectedStrategy,
  savedPersonalStrategy,
  personalBacktest,
  provider,
  onGenerate,
  onGoAction,
  onGoBacktest,
  onGoHome,
}: {
  profile: Profile;
  strategies: StrategyTemplate[];
  selectedStrategy?: StrategyTemplate;
  savedPersonalStrategy?: StrategyTemplate;
  personalBacktest?: BacktestResult;
  provider: ProviderConfigOut | null;
  onGenerate: (payload: PersonalStrategyRequest) => Promise<PersonalStrategyResponse>;
  onGoAction: () => void;
  onGoBacktest: () => void;
  onGoHome: () => void;
}) {
  const [draftProfile, setDraftProfile] = useState(profile);
  const [form, setForm] = useState({
    goals: '长期积累被动收入，优先用指数基金和复利跑赢通胀。',
    investment_horizon: '10年以上',
    drawdown_tolerance: '可以接受中等回撤，但不希望因为过度波动中断计划。',
    preferences: '只买指数基金，希望包含A股宽基、红利、标普500和纳斯达克100。',
    template_hint: selectedStrategy?.id || 'balanced_compound',
  });
  const [result, setResult] = useState<PersonalStrategyResponse | null>(null);
  const [localError, setLocalError] = useState('');
  const [generating, setGenerating] = useState(false);
  const visiblePersonalStrategy = result?.strategy || savedPersonalStrategy;
  const visiblePersonalBacktest = result?.backtest || personalBacktest;

  useEffect(() => {
    setDraftProfile(profile);
  }, [profile]);

  async function submit() {
    setGenerating(true);
    setLocalError('');
    try {
      const response = await onGenerate({ profile: draftProfile, ...form });
      setResult(response);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : '生成个人策略失败');
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="我的策略"
        title="这里就是 AI 个人策略保存的位置。"
        description="生成后会保存为「当前个人策略」，并自动成为首页、行动指南和策略回测使用的默认策略。"
      />
      {localError && <div className="banner danger">{localError}</div>}
      <section className="panel ai-pipeline-panel">
        <div className="card-row">
          <div>
            <span className="eyebrow">AI Native 生成链路</span>
            <h2>访谈不是表单，生成不是文案。</h2>
            <p>Agent 会先理解你的资金和风险边界，再生成长期权重，随后调用回测工具验证历史体验，最后把结果保存为可执行纪律。</p>
          </div>
          <span className="pill">{provider?.api_key_set ? `${provider.provider} 已配置` : '本地顾问兜底'}</span>
        </div>
        <div className="pipeline-steps">
          <div><strong>1 画像访谈</strong><span>资金、周期、回撤承受、偏好限制</span></div>
          <div><strong>2 生成权重</strong><span>只在五类指数资产中分配，不碰个股</span></div>
          <div><strong>3 工具回测</strong><span>调用后端回测引擎，不伪造缺失数据</span></div>
          <div><strong>4 保存纪律</strong><span>进入首页、行动指南和问一问上下文</span></div>
        </div>
      </section>
      <section className="panel saved-strategy-panel">
        <div className="card-row">
          <div>
            <h2>当前保存的个人策略</h2>
            <p>
              {visiblePersonalStrategy
                ? '保存位置：我的策略 / 当前个人策略。系统已把它设为当前策略。'
                : '尚未生成个人策略。生成后会出现在这里。'}
            </p>
          </div>
          <span className="pill">{visiblePersonalStrategy ? '已保存' : '未生成'}</span>
        </div>
        {visiblePersonalStrategy ? (
          <>
            <div className="saved-strategy-main">
              <div>
                <h3>{visiblePersonalStrategy.name}</h3>
                <p>{visiblePersonalStrategy.positioning}</p>
              </div>
              <WeightBars weights={visiblePersonalStrategy.weights} />
            </div>
            {visiblePersonalBacktest && (
              <div className="personal-backtest-summary">
                <div className="card-row">
                  <h3>个人策略历史回测</h3>
                  <span className="pill" title={qualityLabel(visiblePersonalBacktest.data_quality)}>{qualityLabel(visiblePersonalBacktest.data_quality)}</span>
                </div>
                <div className="metric-grid compact-metrics">
                  <Metric label="年化收益" value={fmtPct(visiblePersonalBacktest.annualized_return)} />
                  <Metric label="最大回撤" value={fmtPct(visiblePersonalBacktest.max_drawdown)} />
                  <Metric label="年化波动" value={fmtPct(visiblePersonalBacktest.annualized_volatility)} />
                  <Metric label="期末资产" value={`¥${fmtMoney(visiblePersonalBacktest.final_value)}`} />
                </div>
                <button className="secondary-action" onClick={onGoBacktest} title="查看完整个人策略回测">
                  <LineChart size={18} />
                  <span>查看完整个人回测</span>
                </button>
              </div>
            )}
            <div className="route-list">
              <div><strong>首页</strong><span>显示为当前策略，影响本月建议买入金额。</span></div>
              <div><strong>行动指南</strong><span>用它的权重拆分近期买入和观察重点。</span></div>
              <div><strong>策略回测</strong><span>作为个人策略参与模板对比和执行脚本。</span></div>
            </div>
            <div className="action-row">
              <button className="primary-action" onClick={onGoAction} title="查看这个个人策略生成的近期行动指南">
                <CalendarCheck size={18} />
                <span>用它看行动指南</span>
              </button>
              <button className="secondary-action" onClick={onGoBacktest} title="查看这个个人策略的回测">
                <LineChart size={18} />
                <span>查看策略回测</span>
              </button>
              <button className="secondary-action" onClick={onGoHome} title="回到首页确认当前策略">
                <Landmark size={18} />
                <span>回首页确认</span>
              </button>
            </div>
          </>
        ) : (
          <div className="empty compact">填写下方信息后，点击生成，个人策略会保存到这里。</div>
        )}
      </section>
      <div className="advisor-layout">
        <div className="panel form-panel">
          <h2>投资画像</h2>
          <div className="metric-grid">
            <LabeledInput label="一次性待投资金" value={draftProfile.lump_sum_capital} onChange={(value) => setDraftProfile({ ...draftProfile, lump_sum_capital: value })} />
            <LabeledInput label="每月新增现金流" value={draftProfile.monthly_contribution} onChange={(value) => setDraftProfile({ ...draftProfile, monthly_contribution: value })} />
            <LabeledInput label="当前现金" value={draftProfile.current_cash} onChange={(value) => setDraftProfile({ ...draftProfile, current_cash: value })} />
            <LabeledInput label="应急现金底线" value={draftProfile.emergency_cash_floor} onChange={(value) => setDraftProfile({ ...draftProfile, emergency_cash_floor: value })} />
          </div>
          <label className="field">
            <span>风险偏好</span>
            <select value={draftProfile.risk_preference} onChange={(event) => setDraftProfile({ ...draftProfile, risk_preference: event.target.value as Profile['risk_preference'] })}>
              <option value="conservative">稳健</option>
              <option value="balanced">均衡</option>
              <option value="growth">成长</option>
            </select>
          </label>
          <label className="field">
            <span>计划投完时间</span>
            <input type="number" min="1" max="36" value={draftProfile.investment_months} onChange={(event) => setDraftProfile({ ...draftProfile, investment_months: Number(event.target.value) })} />
          </label>
          <label className="field">
            <span>参考模板</span>
            <select value={form.template_hint} onChange={(event) => setForm({ ...form, template_hint: event.target.value })}>
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>{strategy.name}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="panel form-panel">
          <h2>策略偏好</h2>
          <label className="field">
            <span>目标</span>
            <textarea value={form.goals} onChange={(event) => setForm({ ...form, goals: event.target.value })} />
          </label>
          <label className="field">
            <span>投资周期</span>
            <textarea value={form.investment_horizon} onChange={(event) => setForm({ ...form, investment_horizon: event.target.value })} />
          </label>
          <label className="field">
            <span>回撤承受度</span>
            <textarea value={form.drawdown_tolerance} onChange={(event) => setForm({ ...form, drawdown_tolerance: event.target.value })} />
          </label>
          <label className="field">
            <span>偏好与限制</span>
            <textarea value={form.preferences} onChange={(event) => setForm({ ...form, preferences: event.target.value })} />
          </label>
          <button className="primary-action" onClick={submit} disabled={generating} title="生成个人策略草案">
            <Brain size={18} />
            <span>{generating ? '生成中' : provider?.api_key_set ? '让 DeepSeek 生成个人策略' : '生成本地个人策略'}</span>
          </button>
          <p className="fine-print">
            当前模型：{provider?.api_key_set ? `${provider.provider} / ${provider.model}` : '未配置 API Key，将使用本地策略顾问兜底'}。
          </p>
        </div>

        <div className="panel advisor-result">
          <h2>{result ? '本次生成说明' : '保存说明'}</h2>
          {!result && (
            <div className="empty compact">
              {selectedStrategy?.is_personalized || savedPersonalStrategy
                ? '上方已经显示当前保存的个人策略。重新生成会覆盖当前个人策略。'
                : '生成后会保存到上方「当前保存的个人策略」，并自动进入行动指南和回测。'}
            </div>
          )}
          {result && (
            <>
              <div className="card-row">
                <div>
                  <h3>已保存为：{result.strategy.name}</h3>
                  <p>保存位置：我的策略 / 当前个人策略。后续纪律计划已使用这个策略。</p>
                </div>
                <span className="pill">{result.fallback ? '本地顾问' : 'DeepSeek'}</span>
              </div>
              <p className="explain-box">{result.explanation}</p>
              {result.backtest && (
                <div className="personal-backtest-summary">
                  <div className="card-row">
                    <h3>个人策略历史回测</h3>
                    <span className="pill" title={qualityLabel(result.backtest.data_quality)}>{qualityLabel(result.backtest.data_quality)}</span>
                  </div>
                  <div className="metric-grid compact-metrics">
                    <Metric label="年化收益" value={fmtPct(result.backtest.annualized_return)} />
                    <Metric label="最大回撤" value={fmtPct(result.backtest.max_drawdown)} />
                    <Metric label="年化波动" value={fmtPct(result.backtest.annualized_volatility)} />
                    <Metric label="期末资产" value={`¥${fmtMoney(result.backtest.final_value)}`} />
                  </div>
                  <button className="secondary-action" onClick={onGoBacktest} title="查看完整个人策略回测">
                    <LineChart size={18} />
                    <span>查看完整回测</span>
                  </button>
                </div>
              )}
              <ul className="note-list">
                {result.strategy.risks.map((risk) => <li key={risk}>{risk}</li>)}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function BacktestPage({
  strategies,
  backtests,
  profile,
  selectedId,
  historyStatus,
  historyRefreshing,
  onSelectStrategy,
  onRefreshHistory,
}: {
  strategies: StrategyTemplate[];
  backtests: BacktestResult[];
  profile: Profile;
  selectedId: string;
  historyStatus: HistoricalDataStatus | null;
  historyRefreshing: boolean;
  onSelectStrategy: (id: string) => void;
  onRefreshHistory: () => void;
}) {
  const [rangeStart, setRangeStart] = useState('2016-01');
  const [rangeEnd, setRangeEnd] = useState(() => new Date().toISOString().slice(0, 7));
  const [rangeResult, setRangeResult] = useState<BacktestResult | null>(null);
  const [rangeLoading, setRangeLoading] = useState(false);
  const [rangeError, setRangeError] = useState('');
  const defaultSelected = backtests.find((item) => item.strategy_id === selectedId) || backtests[0];
  const selected = rangeResult?.strategy_id === selectedId ? rangeResult : defaultSelected;
  const selectedStrategy = strategies.find((item) => item.id === selectedId);
  const readySources = historyStatus?.sources.filter((source) => source.data_quality === 'HISTORY_CACHE_READY').length || 0;
  const historyEndDates = (historyStatus?.sources || []).map((source) => source.end_date).filter(Boolean).sort();
  const latestHistoryDate = historyEndDates.length ? historyEndDates[historyEndDates.length - 1] : '';
  const latestHistoryMonth = latestHistoryDate ? latestHistoryDate.slice(0, 7) : new Date().toISOString().slice(0, 7);

  useEffect(() => {
    setRangeEnd(latestHistoryMonth);
  }, [latestHistoryMonth]);

  const handleSelectStrategy = (id: string) => {
    setRangeResult(null);
    setRangeError('');
    onSelectStrategy(id);
  };

  const handleRunRangeBacktest = async () => {
    if (!/^\d{4}-\d{2}$/.test(rangeStart) || !/^\d{4}-\d{2}$/.test(rangeEnd)) {
      setRangeError('请输入 YYYY-MM 格式，例如 2020-01。');
      return;
    }
    setRangeLoading(true);
    setRangeError('');
    try {
      const result = await api.runBacktest(
        selectedId,
        profile.lump_sum_capital,
        profile.monthly_contribution,
        rangeStart,
        rangeEnd,
      );
      setRangeResult(result);
    } catch (error) {
      setRangeError(error instanceof Error ? error.message : '区间回测失败');
    } finally {
      setRangeLoading(false);
    }
  };

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="回测认知"
        title="比较策略，不比较幻想。"
        description="收益必须和回撤、波动、最长回本时间一起看。回测优先调用本地历史行情工具，数据不足时必须显示降级标签。"
      />
      <div className="panel data-tool-panel">
        <div>
          <h2>历史数据工具</h2>
          <p>
            当前缓存：{qualityLabel(historyStatus?.data_quality)} · {readySources}/{historyStatus?.sources.length || 5} 类资产可用于历史回测。
            数据来自东方财富日K线，本地 SQLite 缓存后供 Agent 和回测引擎调用。
          </p>
          <p className="fine-print">
            {historyStatus?.auto_refresh_message || '打开页面时会自动检查一次历史数据；今天已检查过则跳过，不会重复请求数据源。'}
            {historyStatus?.last_refresh_at ? ` 最近检查：${new Date(historyStatus.last_refresh_at).toLocaleString('zh-CN')}` : ''}
          </p>
        </div>
        <button className="secondary-action" onClick={onRefreshHistory} disabled={historyRefreshing} title="刷新历史行情并重新计算策略回测">
          <RefreshCw size={18} />
          <span>{historyRefreshing ? '刷新中' : '刷新历史数据'}</span>
        </button>
      </div>
      <div className="history-source-grid">
        {(historyStatus?.sources || []).map((source) => (
          <div className="history-source-card" key={source.asset_key}>
            <div>
              <strong>{source.name}</strong>
              <span>{qualityLabel(source.data_quality)}</span>
            </div>
            <p>{source.start_date || '无缓存'} 至 {source.end_date || '无缓存'}</p>
            <em>{source.source_symbol} · {source.source}</em>
          </div>
        ))}
      </div>
      <div className="panel range-backtest-panel">
        <div>
          <h2>自定义区间回测</h2>
          <p>
            默认结束到最新缓存月份{latestHistoryDate ? `（最新交易日 ${latestHistoryDate}）` : ''}。如果某段数据缺失，结果会在“回测边界”里列出，不会静默补齐。
          </p>
        </div>
        <label>
          <span>开始月份</span>
          <input type="text" inputMode="numeric" pattern="[0-9]{4}-[0-9]{2}" placeholder="2020-01" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} />
        </label>
        <label>
          <span>结束月份</span>
          <input type="text" inputMode="numeric" pattern="[0-9]{4}-[0-9]{2}" placeholder={latestHistoryMonth} value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} />
        </label>
        <button className="primary-action" onClick={handleRunRangeBacktest} disabled={rangeLoading || !rangeStart || !rangeEnd}>
          <LineChart size={18} />
          <span>{rangeLoading ? '计算中' : '按区间回测'}</span>
        </button>
      </div>
      {rangeError && <div className="notice error">{rangeError}</div>}
      {rangeResult && (
        <div className="notice">
          已切换为 {rangeResult.strategy_name} 的区间回测结果：{rangeResult.equity_curve[0]?.date} 至 {rangeResult.equity_curve[rangeResult.equity_curve.length - 1]?.date}。
        </div>
      )}
      <div className="comparison-table panel">
        <table>
          <thead>
            <tr>
              <th>策略</th>
              <th>年化</th>
              <th>最大回撤</th>
              <th>波动</th>
              <th>最差年份</th>
              <th>最长回本</th>
              <th>近5年</th>
            </tr>
          </thead>
          <tbody>
            {backtests.map((item) => (
              <tr key={item.strategy_id} className={item.strategy_id === selectedId ? 'selected-row' : ''} onClick={() => handleSelectStrategy(item.strategy_id)}>
                <td>{item.strategy_name}</td>
                <td>{fmtPct(item.annualized_return)}</td>
                <td>{fmtPct(item.max_drawdown)}</td>
                <td>{fmtPct(item.annualized_volatility)}</td>
                <td>{item.worst_year} {fmtSignedPct(item.worst_year_return)}</td>
                <td>{item.longest_recovery_months} 月</td>
                <td>{fmtPct(item.trailing_returns['5y'] || 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="dashboard-grid two">
        <BacktestExecutionPanel
          result={selected}
          strategy={selectedStrategy}
          profile={profile}
        />
        <div className="panel">
          <h2>净值曲线</h2>
          {selected && <EquityCurve points={selected.equity_curve} large />}
          <p className="fine-print">这条曲线来自左侧执行脚本：初始按权重建仓、每月按权重买入、每年再平衡。若数据质量为历史行情，曲线由历史月度收益生成；若为代理降级，则只能作认知辅助。</p>
        </div>
      </div>
      <div className="dashboard-grid two">
        <div className="panel">
          <h2>策略解释</h2>
          {selectedStrategy && (
            <StrategyDetail strategy={selectedStrategy} />
          )}
        </div>
        <div className="panel warning-panel">
          <h2>回测边界</h2>
          <ul className="note-list">
            {selected?.notes.map((note) => <li key={note}>{note}</li>)}
            <li>回测里的“卖出”只来自年度再平衡，不做短线逃顶；近期行动指南会基于真实市场温度单独判断是否需要卖出提醒。</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function BacktestExecutionPanel({
  result,
  strategy,
  profile,
}: {
  result?: BacktestResult;
  strategy?: StrategyTemplate;
  profile: Profile;
}) {
  if (!result || !strategy) {
    return <div className="panel">暂无回测执行说明。</div>;
  }
  const profit = result.final_value - result.total_contributed;
  const profitRate = result.total_contributed > 0 ? profit / result.total_contributed : 0;
  const startDate = result.equity_curve[0]?.date.replace('-00', '-初始') || '-';
  const endDate = result.equity_curve[result.equity_curve.length - 1]?.date || '-';
  const monthlyRows = Object.entries(strategy.weights).map(([key, weight]) => ({
    key: key as AssetKey,
    weight,
    initial: profile.lump_sum_capital * weight,
    monthly: profile.monthly_contribution * weight,
  }));

  return (
    <div className="panel backtest-script">
      <div className="card-row">
        <div>
          <h2>{result.strategy_name} 执行脚本</h2>
          <p>{startDate} 到 {endDate}</p>
        </div>
        <span className="pill" title={qualityLabel(result.data_quality)}>{qualityLabel(result.data_quality)}</span>
      </div>
      <div className="metric-grid">
        <Metric label="计划初始资金" value={`¥${fmtMoney(profile.lump_sum_capital)}`} />
        <Metric label="每月买入" value={`¥${fmtMoney(profile.monthly_contribution)}`} />
        <Metric label="累计投入" value={`¥${fmtMoney(result.total_contributed)}`} />
        <Metric label="期末资产" value={`¥${fmtMoney(result.final_value)}`} />
        <Metric label="累计盈利" value={`¥${fmtMoney(profit)}`} sub={fmtSignedPct(profitRate)} />
        <Metric label="最大回撤" value={fmtPct(result.max_drawdown)} />
      </div>
      <div className="execution-steps">
        <div><strong>初始建仓</strong><span>一次性资金按目标权重买入，不择时一次猜底。</span></div>
        <div><strong>每月定投</strong><span>每月固定买入，金额按策略权重拆分。</span></div>
        <div><strong>年度再平衡</strong><span>每年检查一次，卖出明显超配资产、补足低配资产。</span></div>
        <div><strong>卖出边界</strong><span>回测不做预测型卖出，只模拟再平衡卖出。</span></div>
      </div>
      <div className="trade-breakdown">
        <div className="trade-breakdown-head">
          <span>指数</span>
          <span>目标</span>
          <span>初始买入</span>
          <span>每月买入</span>
        </div>
        {monthlyRows.map((row) => (
          <div className="trade-breakdown-row" key={row.key}>
            <span>{assetLabels[row.key]}</span>
            <strong>{Math.round(row.weight * 100)}%</strong>
            <strong>¥{fmtMoney(row.initial)}</strong>
            <strong>¥{fmtMoney(row.monthly)}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function ActionGuidePage({
  profile,
  market,
  plan,
  selectedStrategy,
  onRefresh,
  refreshing,
}: {
  profile: Profile;
  market: MarketSnapshot | null;
  plan: MonthlyPlan | null;
  selectedStrategy?: StrategyTemplate;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  if (!plan) {
    return (
      <div className="page-stack">
        <PageHeader
          eyebrow="近期行动指南"
          title="先生成计划，再看近期动作。"
          description="行动指南基于当前策略、现金池和每日市场温度生成。"
        />
        <div className="panel">暂无月度计划。</div>
      </div>
    );
  }

  const marketMap = new Map(market?.assets.map((asset) => [asset.asset_key, asset]) || []);
  const totalHolding = Object.values(profile.holdings || {}).reduce((sum, value) => sum + Math.max(value || 0, 0), 0);
  const rows = plan.allocations.map((allocation) => {
    const snapshot = marketMap.get(allocation.asset_key);
    const temperature = snapshot?.temperature ?? allocation.temperature;
    const holding = Math.max(profile.holdings?.[allocation.asset_key] || 0, 0);
    const actualWeight = totalHolding > 0 ? holding / totalHolding : null;
    const drift = actualWeight == null ? null : actualWeight - allocation.target_weight;
    const overweightValue = drift != null && drift > 0 ? drift * totalHolding : 0;
    const sellAmount = temperature >= 80 && overweightValue > 0 ? Math.round(overweightValue * 0.2) : 0;
    const status = actionStatusForTemperature(temperature, sellAmount, plan.multiplier);
    const timing = actionTimingForTemperature(temperature, sellAmount, plan.multiplier);
    const buyText = plan.multiplier === 0 ? '暂停新增买入' : `买入 ¥${fmtMoney(allocation.amount)}`;
    const sellText = sellAmount > 0 ? `；复核后可卖出约 ¥${fmtMoney(sellAmount)} 转入现金池` : '';
    return {
      ...allocation,
      snapshot,
      temperature,
      holding,
      drift,
      sellAmount,
      status,
      timing,
      action: `${buyText}${sellText}`,
    };
  });
  const focusRows = [...rows]
    .sort((a, b) => {
      if (b.sellAmount !== a.sellAmount) return b.sellAmount - a.sellAmount;
      return a.temperature - b.temperature;
    })
    .slice(0, 3);
  const sellRows = rows.filter((row) => row.sellAmount > 0);
  const executionWindow =
    plan.multiplier === 0
      ? '先补现金安全垫，本期不新增买入'
      : plan.average_temperature < 45
      ? '未来7天内优先执行低温部分'
      : plan.average_temperature >= 65
      ? '只在固定定投日执行，不额外加仓'
      : '本月固定定投日执行即可';

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="近期行动指南"
        title="把每日评估翻译成最近该做什么。"
        description="这里不是短线交易信号，而是把当前策略、现金池和指数温度转成可执行的买入、观察和卖出复核清单。"
      />
      <div className="panel market-overview">
        <div>
          <h2>{selectedStrategy?.name || plan.strategy_name}</h2>
          <p>{qualityLabel(market?.data_quality || plan.data_quality_status)} · {market ? `市场日期 ${market.assets[0]?.as_of || '-'}` : '市场数据未加载'}</p>
        </div>
        <button className="primary-action" onClick={onRefresh} disabled={refreshing} title="刷新今日评估并重算行动指南">
          <RefreshCw size={18} />
          <span>{refreshing ? '刷新中' : '刷新今日评估'}</span>
        </button>
      </div>

      <section className="action-summary-grid">
        <Metric label="本期合计买入" value={`¥${fmtMoney(plan.suggested_total_buy)}`} sub={`${plan.temperature_band} · 倍率 ${plan.multiplier}`} />
        <Metric label="执行窗口" value={executionWindow} />
        <Metric label="重点关注" value={focusRows.map((row) => assetLabels[row.asset_key]).join('、') || '-'} />
        <Metric label="卖出提醒" value={sellRows.length ? `${sellRows.length} 项需复核` : '本期不建议主动卖出'} />
      </section>

      <div className="dashboard-grid two">
        <div className="panel">
          <h2>重点关注指数</h2>
          <div className="focus-list">
            {focusRows.map((row) => (
              <div className="focus-item" key={row.asset_key}>
                <div>
                  <strong>{assetLabels[row.asset_key]}</strong>
                  <span>温度 {row.temperature.toFixed(0)} · {row.status}</span>
                </div>
                <p>{row.action}</p>
                <em>{row.timing}</em>
              </div>
            ))}
          </div>
        </div>
        <div className="panel warning-panel">
          <h2>卖出规则边界</h2>
          <ul className="note-list">
            <li>默认不主动卖出，指数基金策略以长期持有和新增资金修正为主。</li>
            <li>只有指数温度极热，且已录入持仓显示明显超配时，才提示卖出超配部分的一小段。</li>
            <li>未录入持仓时，系统不会编造卖出金额，只提示继续观察或按月少买。</li>
          </ul>
        </div>
      </div>

      <div className="panel action-table-panel">
        <h2>逐指数近期动作</h2>
        <div className="action-table">
          <div className="action-table-head">
            <span>指数</span>
            <span>温度</span>
            <span>状态</span>
            <span>近期动作</span>
            <span>执行时间</span>
          </div>
          {rows.map((row) => (
            <div className="action-table-row" key={row.asset_key}>
              <span>{assetLabels[row.asset_key]}</span>
              <strong>{row.temperature.toFixed(0)}</strong>
              <span className="pill">{row.status}</span>
              <p>{row.action}</p>
              <em>{row.timing}</em>
            </div>
          ))}
        </div>
        <p className="fine-print">金额来自规则引擎：当前策略权重、现金池、市场温度倍率共同决定。产品不自动下单，也不承诺买入后短期上涨。</p>
      </div>
    </div>
  );
}

function actionStatusForTemperature(temperature: number, sellAmount: number, multiplier: number) {
  if (multiplier === 0) return '暂停';
  if (sellAmount > 0) return '卖出复核';
  if (temperature < 25) return '极冷优先';
  if (temperature < 45) return '偏冷加码';
  if (temperature < 65) return '正常定投';
  if (temperature < 80) return '偏热减速';
  return '极热观察';
}

function actionTimingForTemperature(temperature: number, sellAmount: number, multiplier: number) {
  if (multiplier === 0) return '现金低于安全垫前不执行新增买入';
  if (sellAmount > 0) return '本周复核持仓，确认严重超配后再执行';
  if (temperature < 45) return '最近一个交易日或本月第一笔定投优先执行';
  if (temperature < 65) return '本月固定定投日执行';
  if (temperature < 80) return '只在固定定投日执行，不追涨补仓';
  return '等待固定定投日，禁止额外加仓';
}

function PlanPage({ profile, setProfile, cashPool, setCashPool, strategies, onSave, plan }: {
  profile: Profile;
  setProfile: (profile: Profile) => void;
  cashPool: CashPool;
  setCashPool: (cashPool: CashPool) => void;
  strategies: StrategyTemplate[];
  onSave: (profile?: Profile, cashPool?: CashPool) => void;
  plan: MonthlyPlan | null;
}) {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="计划配置"
        title="把准备投的钱拆清楚，再决定本月买多少。"
        description="这里的目标是纪律，不是刺激。先保应急现金，再让排队资金按节奏进入指数。"
      />
      <div className="dashboard-grid two">
        <div className="panel form-panel">
          <h2>资金与策略</h2>
          <LabeledInput label="一次性待投资金" value={profile.lump_sum_capital} onChange={(value) => setProfile({ ...profile, lump_sum_capital: value })} />
          <LabeledInput label="每月新增现金流" value={profile.monthly_contribution} onChange={(value) => setProfile({ ...profile, monthly_contribution: value })} />
          <LabeledInput label="应急现金底线" value={profile.emergency_cash_floor} onChange={(value) => setProfile({ ...profile, emergency_cash_floor: value })} />
          <LabeledInput label="当前现金" value={profile.current_cash} onChange={(value) => setProfile({ ...profile, current_cash: value })} />
          <label className="field">
            <span>默认策略</span>
            <select value={profile.selected_strategy_id} onChange={(event) => setProfile({ ...profile, selected_strategy_id: event.target.value })}>
              {strategies.map((strategy) => (
                <option key={strategy.id} value={strategy.id}>{strategy.name}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>计划投完时间</span>
            <input type="number" min="1" max="36" value={profile.investment_months} onChange={(event) => setProfile({ ...profile, investment_months: Number(event.target.value) })} />
          </label>
          <button className="primary-action" onClick={() => onSave(profile, cashPool)} title="保存配置并刷新计划">
            <Save size={18} />
            <span>保存并生成计划</span>
          </button>
        </div>
        <PlanSummary plan={plan} explanation="" onSaveRecord={() => undefined} compact />
      </div>
    </div>
  );
}

function MarketPage({
  market,
  plan,
  onRefresh,
  refreshing,
}: {
  market: MarketSnapshot | null;
  plan: MonthlyPlan | null;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="每日指数评估"
        title="每天看大盘温度，每月执行一次纪律动作。"
        description="指数基金不需要秒级交易，但需要持续知道各指数处于什么温度。真实K线、代理数据和缺失项都会明确标注。"
      />
      <div className="panel market-overview">
        <div>
          <h2>今日数据状态</h2>
          <p>{qualityLabel(market?.data_quality)} · 生成时间 {market ? new Date(market.generated_at).toLocaleString('zh-CN') : '-'}</p>
        </div>
        <button className="primary-action" onClick={onRefresh} disabled={refreshing} title="刷新真实市场数据">
          <RefreshCw size={18} />
          <span>{refreshing ? '刷新中' : '刷新真实市场数据'}</span>
        </button>
      </div>
      {market?.notes.length ? (
        <div className="panel">
          <h2>数据说明</h2>
          <ul className="note-list">{market.notes.map((note) => <li key={note}>{note}</li>)}</ul>
        </div>
      ) : null}
      <div className="market-grid">
        {market?.assets.map((asset) => (
          <div className="panel market-card" key={asset.asset_key}>
            <div className="card-row">
              <h2>{asset.name}</h2>
              <span className={asset.is_live ? 'pill success-pill' : 'pill'}>{asset.is_live ? '真实K线' : '代理'}</span>
            </div>
            <TemperatureGauge value={asset.temperature} />
            <div className="metric-grid">
              <Metric label="最新价格" value={asset.price.toFixed(2)} />
              <Metric label="建议节奏" value={multiplierRangeForTemperature(asset.temperature)} />
              <Metric label="估值分位" value={asset.valuation_percentile == null ? '缺失' : `${asset.valuation_percentile.toFixed(0)}`} />
              <Metric label="200日位置" value={fmtSignedPct(asset.ma200_position)} />
              <Metric label="回撤" value={fmtPct(asset.drawdown)} />
              <Metric label="波动" value={fmtPct(asset.volatility)} />
            </div>
            <div className="source-list">
              <span>来源 <strong>{asset.source}</strong></span>
              <span>代码 <strong>{asset.source_symbol || '-'}</strong></span>
              <span>日期 <strong>{asset.as_of || '-'}</strong></span>
              <span>质量 <strong title={qualityLabel(asset.data_quality)}>{qualityLabel(asset.data_quality)}</strong></span>
            </div>
            <ul className="note-list">
              {asset.notes.map((note) => <li key={note}>{note}</li>)}
            </ul>
          </div>
        ))}
      </div>
      {plan && (
        <div className="panel">
          <h2>组合温度结论</h2>
          <p className="lead">当前组合温度 {plan.average_temperature}，处于「{plan.temperature_band}」，规则倍率为 {plan.multiplier}。</p>
        </div>
      )}
    </div>
  );
}

function CashPage({ profile, setProfile, cashPool, setCashPool, onSave }: {
  profile: Profile;
  setProfile: (profile: Profile) => void;
  cashPool: CashPool;
  setCashPool: (cashPool: CashPool) => void;
  onSave: (profile?: Profile, cashPool?: CashPool) => void;
}) {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="待投资金池"
        title="还没买进去的钱，也要有纪律。"
        description="现金池的作用是保流动性、等待定投节奏、等待低温机会，不是追求高收益。"
      />
      <div className="dashboard-grid two">
        <div className="panel">
          <h2>现金池结构</h2>
          <CashSplit cashPool={cashPool} />
          <div className="form-panel">
            <LabeledInput label="应急现金" value={cashPool.emergency_cash} onChange={(value) => setCashPool({ ...cashPool, emergency_cash: value })} />
            <LabeledInput label="定投排队资金" value={cashPool.queue_cash} onChange={(value) => setCashPool({ ...cashPool, queue_cash: value })} />
            <LabeledInput label="机会资金" value={cashPool.opportunity_cash} onChange={(value) => setCashPool({ ...cashPool, opportunity_cash: value })} />
            <label className="field">
              <span>建议停放工具</span>
              <input value={cashPool.parking_tool} onChange={(event) => setCashPool({ ...cashPool, parking_tool: event.target.value })} />
            </label>
            <button className="primary-action" onClick={() => onSave(profile, cashPool)} title="保存现金池">
              <Save size={18} />
              <span>保存现金池</span>
            </button>
          </div>
        </div>
        <div className="panel">
          <h2>现金纪律</h2>
          <div className="principles">
            <div><strong>应急现金</strong><span>不参与投资计划，用来覆盖生活风险。</span></div>
            <div><strong>排队资金</strong><span>未来 6-18 个月逐步进入指数，不因短期新闻乱动。</span></div>
            <div><strong>机会资金</strong><span>市场极冷时提前动用，但仍不突破安全垫。</span></div>
            <div><strong>停放工具</strong><span>偏向高流动性、低波动工具；不描述为保本。</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}

function DividendPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="红利防守权益"
        title="红利给的是现金流感，不是无风险利息。"
        description="中证红利、红利低波适合作为权益仓里的防守模块，但它们仍然是股票资产。"
      />
      <div className="dashboard-grid two">
        <div className="panel">
          <h2>红利模块适合做什么</h2>
          <div className="principles">
            <div><strong>成熟企业</strong><span>偏向有分红记录和现金流的公司。</span></div>
            <div><strong>分红再投</strong><span>积累期默认再投资，让复利更完整。</span></div>
            <div><strong>组合缓冲</strong><span>在成长资产剧烈波动时，红利通常更像防守权益。</span></div>
            <div><strong>未来现金流</strong><span>到需要被动现金流时，再考虑现金分红。</span></div>
          </div>
        </div>
        <div className="panel warning-panel">
          <h2>必须看到的风险</h2>
          <ul className="note-list">
            <li>红利基金不是债券，也不是银行理财，会随股票市场下跌。</li>
            <li>高股息可能来自股价大跌或盈利恶化，需要警惕高股息陷阱。</li>
            <li>行业集中度可能偏高，极端时期也会出现明显回撤。</li>
            <li>牛市中红利弹性可能弱于科技成长策略。</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function EducationPage() {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="复利科普"
        title="普通人的优势，是可以承认自己不懂。"
        description="低成本、分散、长期、少交易，这些朴素的东西，往往比追逐短期聪明更可靠。"
      />
      <div className="education-layout">
        <section className="panel">
          <h2>巴菲特式普通人指数投资</h2>
          <p className="lead">
            普通人不必挑赢家，也不必每天预测市场。拥有一篮子优秀企业，控制成本，坚持定期投入，长期结果反而可能好过许多高成本主动管理。
          </p>
          <div className="principles">
            <div><strong>低成本</strong><span>少交管理费和交易摩擦，收益更容易留在自己手里。</span></div>
            <div><strong>足够分散</strong><span>买的是一批企业，不把命运押在单家公司上。</span></div>
            <div><strong>长期投入</strong><span>不是靠一次买点，而是让现金流持续进入资产。</span></div>
            <div><strong>温度增强</strong><span>便宜时多买一点，昂贵时少买一点，但不幻想精准抄底逃顶。</span></div>
          </div>
        </section>
        <section className="panel">
          <h2>产品边界</h2>
          <ul className="note-list">
            <li>不承诺收益，不说指数永远不会死。</li>
            <li>不自动下单，不接券商。</li>
            <li>不推荐个股、主动基金和行业主题基金。</li>
            <li>AI 只解释规则引擎结果，不能覆盖金额建议。</li>
          </ul>
        </section>
      </div>
    </div>
  );
}

function RecordsPage({
  records,
  review,
  onMark,
  onRefreshReview,
}: {
  records: InvestmentRecord[];
  review: DisciplineReview | null;
  onMark: (record: InvestmentRecord, executed: boolean) => void;
  onRefreshReview: () => void;
}) {
  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="投资记录"
        title="记录不是为了后悔，是为了抵抗情绪。"
        description="每次建议都保存输入、规则结果和解释，后续可以复盘纪律是否被执行。"
      />
      <section className="panel discipline-panel">
        <div className="card-row">
          <div>
            <span className="eyebrow">AI 纪律复盘</span>
            <h2>{review ? `执行纪律分 ${review.score}` : '等待复盘记录'}</h2>
            <p>{review?.summary || '保存并标记执行状态后，Agent 会复盘你是否偏离长期纪律。'}</p>
          </div>
          <button className="secondary-action" onClick={onRefreshReview} title="刷新纪律复盘">
            <RefreshCw size={18} />
            <span>刷新复盘</span>
          </button>
        </div>
        <div className="discipline-grid">
          <div>
            <h3>观察</h3>
            <ul className="note-list">
              {(review?.observations || ['暂无足够记录。']).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
          <div>
            <h3>修正动作</h3>
            <ul className="note-list">
              {(review?.next_actions || ['先保存本月建议，再标记是否执行。']).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
      </section>
      <div className="record-list">
        {records.length === 0 && <div className="panel empty">暂无记录。可以在首页保存本月建议。</div>}
        {records.map((record) => (
          <article className="panel record-card" key={record.id}>
            <div className="card-row">
              <div>
                <h2>{record.plan.strategy_name}</h2>
                <p>{new Date(record.created_at).toLocaleString('zh-CN')}</p>
              </div>
              <span className={record.executed ? 'pill success-pill' : 'pill'}>{record.executed ? '已执行' : '待执行'}</span>
            </div>
            <div className="metric-grid">
              <Metric label="建议买入" value={`¥${fmtMoney(record.plan.suggested_total_buy)}`} />
              <Metric label="市场温度" value={`${record.plan.average_temperature}`} sub={record.plan.temperature_band} />
              <Metric label="倍率" value={`${record.plan.multiplier}`} />
            </div>
            <p className="explain-box">{record.ai_explanation || record.plan.education_message}</p>
            <div className="action-row">
              <button className="secondary-action" disabled={record.executed} onClick={() => onMark(record, true)}>
                {record.executed ? '已执行' : '标记已执行'}
              </button>
              <button className="secondary-action" disabled={!record.executed} onClick={() => onMark(record, false)}>
                {record.executed ? '改回待执行' : '待执行中'}
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function SettingsPage({ provider, onSaved }: { provider: ProviderConfigOut | null; onSaved: () => void }) {
  const [form, setForm] = useState({
    provider: provider?.provider || 'deepseek',
    base_url: provider?.base_url || 'https://api.deepseek.com',
    api_key: '',
    model: provider?.model || 'deepseek-chat',
    temperature: provider?.temperature || 0.3,
  });
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (provider) {
      setForm({
        provider: provider.provider,
        base_url: provider.base_url,
        api_key: '',
        model: provider.model,
        temperature: provider.temperature,
      });
    }
  }, [provider]);

  async function save() {
    await api.saveProviderConfig(form);
    await onSaved();
    setMessage('模型配置已保存。API Key 只在本地后端保存，页面不回显明文。');
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="设置"
        title="AI 是解释器，不是决策者。"
        description="这里兼容 OpenAI Chat Completions 风格接口，不限 DeepSeek。没有 API Key 时，系统仍会使用本地规则完整运行。"
      />
      <div className="panel form-panel narrow">
        <h2>模型配置</h2>
        <div className="settings-help">
          <strong>兼容 OpenAI 接口</strong>
          <span>Provider 只是你给服务商起的名字；Base URL 填兼容 OpenAI 的接口地址；Model 填该服务商的模型名。DeepSeek、OpenAI 兼容代理、本地兼容服务都可以接入。</span>
        </div>
        <label className="field"><span>Provider</span><input value={form.provider} onChange={(event) => setForm({ ...form, provider: event.target.value })} /></label>
        <label className="field"><span>Base URL</span><input value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} /></label>
        <label className="field"><span>API Key</span><input type="password" placeholder={provider?.api_key_set ? provider.api_key_mask : '未设置'} value={form.api_key} onChange={(event) => setForm({ ...form, api_key: event.target.value })} /></label>
        <label className="field"><span>Model</span><input value={form.model} onChange={(event) => setForm({ ...form, model: event.target.value })} /></label>
        <label className="field"><span>Temperature</span><input type="number" min="0" max="2" step="0.1" value={form.temperature} onChange={(event) => setForm({ ...form, temperature: Number(event.target.value) })} /></label>
        <button className="primary-action" onClick={save} title="保存模型配置"><Save size={18} /><span>保存设置</span></button>
        {message && <p className="fine-print">{message}</p>}
      </div>
    </div>
  );
}

function PlanSummary({ plan, explanation, onSaveRecord, compact = false, saved = false }: {
  plan: MonthlyPlan | null;
  explanation: string;
  onSaveRecord: () => void;
  compact?: boolean;
  saved?: boolean;
}) {
  if (!plan) {
    return <div className="panel">暂无计划。</div>;
  }
  return (
    <div className="panel plan-summary">
      <div className="card-row">
        <div>
          <h2>当前策略的本月纪律动作</h2>
          <p>{plan.strategy_name} · {plan.temperature_band}</p>
        </div>
        <span className="pill" title={qualityLabel(plan.data_quality_status)}>{qualityLabel(plan.data_quality_status)}</span>
      </div>
      <div className="hero-number">
        <span>建议买入</span>
        <strong>¥{fmtMoney(plan.suggested_total_buy)}</strong>
      </div>
      <div className="metric-grid compact-metrics">
        <Metric label="基础月投入" value={`¥${fmtMoney(plan.base_amount)}`} />
        <Metric label="温度倍率" value={`${plan.multiplier}`} />
      </div>
      <div className="allocation-list">
        {plan.allocations.map((item) => (
          <div className="allocation-row" key={item.asset_key}>
            <span>{item.name}</span>
            <div className="allocation-bar"><i style={{ width: `${item.target_weight * 100}%` }} /></div>
            <strong>¥{fmtMoney(item.amount)}</strong>
          </div>
        ))}
      </div>
      {!compact && explanation && <p className="explain-box">{explanation}</p>}
      <ul className="note-list">
        {plan.risk_notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
      {!compact && (
        <button className="primary-action" onClick={onSaveRecord} disabled={saved} title={saved ? '本次建议已经保存' : '保存投资建议'}>
          <Save size={18} />
          <span>{saved ? '本次建议已保存' : '保存本次建议'}</span>
        </button>
      )}
    </div>
  );
}

function StrategyDetail({ strategy }: { strategy: StrategyTemplate }) {
  return (
    <div className="strategy-detail">
      <p className="lead">{strategy.positioning}</p>
      <h3>适合人群</h3>
      <p>{strategy.audience}</p>
      <h3>收益来源</h3>
      <ul className="note-list">{strategy.return_sources.map((item) => <li key={item}>{item}</li>)}</ul>
      <h3>主要风险</h3>
      <ul className="note-list">{strategy.risks.map((item) => <li key={item}>{item}</li>)}</ul>
      <WeightBars weights={strategy.weights} />
    </div>
  );
}

function WeightBars({ weights }: { weights: Record<string, number> }) {
  return (
    <div className="weight-bars">
      {Object.entries(weights).map(([key, value]) => (
        <div key={key} className="weight-row">
          <span>{assetLabels[key as AssetKey]}</span>
          <i><b style={{ width: `${value * 100}%` }} /></i>
          <strong>{Math.round(value * 100)}%</strong>
        </div>
      ))}
    </div>
  );
}

function EquityCurve({ points, large = false }: { points: { nav: number; date: string }[]; large?: boolean }) {
  if (!points.length) return null;
  const width = 760;
  const height = large ? 320 : 210;
  const margin = { top: 18, right: 18, bottom: 38, left: 52 };
  const chartWidth = width - margin.left - margin.right;
  const chartHeight = height - margin.top - margin.bottom;
  const values = points.map((point) => point.nav);
  const rawMax = Math.max(...values);
  const rawMin = Math.min(...values);
  const padding = Math.max((rawMax - rawMin) * 0.08, 0.05);
  const max = rawMax + padding;
  const min = Math.max(0, rawMin - padding);
  const range = Math.max(max - min, 0.01);
  const step = Math.max(1, Math.ceil(points.length / 90));
  const sampled = points.filter((_, index) => index % step === 0 || index === points.length - 1);
  const xFor = (index: number) => margin.left + (sampled.length <= 1 ? 0 : (index / (sampled.length - 1)) * chartWidth);
  const yFor = (nav: number) => margin.top + ((max - nav) / range) * chartHeight;
  const linePath = sampled.map((point, index) => `${index === 0 ? 'M' : 'L'} ${xFor(index).toFixed(2)} ${yFor(point.nav).toFixed(2)}`).join(' ');
  const firstX = xFor(0);
  const lastX = xFor(sampled.length - 1);
  const baseY = margin.top + chartHeight;
  const areaPath = `${linePath} L ${lastX.toFixed(2)} ${baseY.toFixed(2)} L ${firstX.toFixed(2)} ${baseY.toFixed(2)} Z`;
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((ratio) => {
    const value = min + range * ratio;
    return { value, y: yFor(value) };
  });
  const xTickIndexes = [0, Math.round((sampled.length - 1) / 3), Math.round(((sampled.length - 1) * 2) / 3), sampled.length - 1]
    .filter((index, position, list) => index >= 0 && list.indexOf(index) === position);
  const xTicks = xTickIndexes.map((index) => ({
    x: xFor(index),
    label: sampled[index].date.slice(0, 4),
  }));
  const formatCurveDate = (date: string) => (date.endsWith('-00') ? `${date.slice(0, 4)} 初始` : date.slice(0, 7));
  const start = points[0];
  const end = points[points.length - 1];
  const peak = points.reduce((best, point) => (point.nav > best.nav ? point : best), points[0]);
  return (
    <div className={large ? 'curve large' : 'curve'}>
      <svg className="curve-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="策略回测净值曲线，横轴为年份，纵轴为净值">
        {yTicks.map((tick) => (
          <g key={tick.value.toFixed(4)}>
            <line className="curve-grid" x1={margin.left} x2={width - margin.right} y1={tick.y} y2={tick.y} />
            <text className="curve-axis-label" x={margin.left - 10} y={tick.y + 4} textAnchor="end">
              {tick.value.toFixed(2)}
            </text>
          </g>
        ))}
        {xTicks.map((tick) => (
          <g key={`${tick.label}-${tick.x}`}>
            <line className="curve-grid curve-grid-vertical" x1={tick.x} x2={tick.x} y1={margin.top} y2={baseY} />
            <text className="curve-axis-label" x={tick.x} y={height - 12} textAnchor="middle">
              {tick.label}
            </text>
          </g>
        ))}
        <line className="curve-axis" x1={margin.left} x2={margin.left} y1={margin.top} y2={baseY} />
        <line className="curve-axis" x1={margin.left} x2={width - margin.right} y1={baseY} y2={baseY} />
        <text className="curve-axis-title" x={14} y={margin.top + chartHeight / 2} transform={`rotate(-90 14 ${margin.top + chartHeight / 2})`} textAnchor="middle">
          净值
        </text>
        <text className="curve-axis-title" x={margin.left + chartWidth / 2} y={height - 2} textAnchor="middle">
          年份
        </text>
        <path className="curve-area" d={areaPath} />
        <path className="curve-line" d={linePath} />
        <circle className="curve-point" cx={xFor(sampled.length - 1)} cy={yFor(end.nav)} r="4" />
      </svg>
      <div className="curve-summary" aria-label="净值曲线摘要">
        <span><b>起点净值</b>{start.nav.toFixed(2)}</span>
        <span><b>期末净值</b>{end.nav.toFixed(2)}</span>
        <span><b>峰值净值</b>{peak.nav.toFixed(2)}</span>
        <span><b>区间</b>{formatCurveDate(start.date)} 至 {formatCurveDate(end.date)}</span>
      </div>
    </div>
  );
}

function CashSplit({ cashPool }: { cashPool: CashPool }) {
  const total = cashPool.emergency_cash + cashPool.queue_cash + cashPool.opportunity_cash || 1;
  const rows = [
    ['应急现金', cashPool.emergency_cash, '#2d7a6d'],
    ['排队资金', cashPool.queue_cash, '#3c68a8'],
    ['机会资金', cashPool.opportunity_cash, '#b96b2c'],
  ] as const;
  return (
    <div className="cash-split">
      {rows.map(([label, value, color]) => (
        <div className="cash-row" key={label}>
          <div>
            <span>{label}</span>
            <strong>¥{fmtMoney(value)}</strong>
          </div>
          <i><b style={{ width: `${(value / total) * 100}%`, background: color }} /></i>
        </div>
      ))}
    </div>
  );
}

function TemperatureGauge({ value }: { value: number }) {
  return (
    <div className="temperature">
      <div className="temp-track"><span style={{ width: `${value}%` }} /></div>
      <div className="temp-labels"><span>冷</span><strong>{value.toFixed(0)}</strong><span>热</span></div>
    </div>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {sub && <em>{sub}</em>}
    </div>
  );
}

function LabeledInput({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type="number" value={value} onChange={(event) => onChange(Number(event.target.value))} />
    </label>
  );
}

const rootElement = document.getElementById('root')!;
const rootWindow = window as typeof window & { __passiveIncomeRoot?: ReturnType<typeof createRoot> };
const root = rootWindow.__passiveIncomeRoot || createRoot(rootElement);
rootWindow.__passiveIncomeRoot = root;

root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
