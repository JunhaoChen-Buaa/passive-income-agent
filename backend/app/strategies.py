from __future__ import annotations

from typing import Dict, List

from .models import AssetKey, FundPoolItem, StrategyTemplate


ASSET_NAMES: Dict[AssetKey, str] = {
    "china_large": "中证A500 / 沪深300",
    "china_mid": "中证500",
    "china_dividend": "中证红利 / 红利低波",
    "sp500": "标普500",
    "nasdaq100": "纳斯达克100",
}


STRATEGIES: List[StrategyTemplate] = [
    StrategyTemplate(
        id="dividend_stable",
        name="稳健红利型",
        level="防守",
        positioning="用较高红利权重降低权益仓波动，保留一部分全球宽基增长。",
        audience="适合看重回撤控制、现金流感和长期持有体验的投资者。",
        return_sources=["高股息公司分红再投资", "成熟企业盈利", "少量美股宽基增长"],
        risks=["红利不是债券，仍会下跌", "行业集中度可能偏高", "牛市弹性通常弱于成长策略"],
        weights={
            "china_large": 0.15,
            "china_mid": 0.10,
            "china_dividend": 0.40,
            "sp500": 0.25,
            "nasdaq100": 0.10,
        },
    ),
    StrategyTemplate(
        id="balanced_compound",
        name="均衡复利型",
        level="默认",
        positioning="A股宽基、红利、美股宽基和科技成长都保留，避免押单一市场。",
        audience="适合多数普通投资者作为长期定投起点。",
        return_sources=["全球企业盈利增长", "红利再投资", "宽基分散", "少量科技成长弹性"],
        risks=["不会在单一牛市中最激进", "A股和美股可能阶段性同时承压", "仍需长期纪律"],
        weights={
            "china_large": 0.20,
            "china_mid": 0.20,
            "china_dividend": 0.15,
            "sp500": 0.30,
            "nasdaq100": 0.15,
        },
    ),
    StrategyTemplate(
        id="us_core",
        name="美股核心型",
        level="进取",
        positioning="以标普500作为核心，搭配少量纳指和A股资产。",
        audience="适合看好美国大盘企业长期竞争力，且能接受汇率和海外估值波动的人。",
        return_sources=["美国大盘企业盈利", "全球化收入", "美元资产敞口", "科技龙头增长"],
        risks=["美股估值偏高时回撤压力大", "汇率会影响人民币收益", "地域集中度较高"],
        weights={
            "china_large": 0.10,
            "china_mid": 0.10,
            "china_dividend": 0.10,
            "sp500": 0.50,
            "nasdaq100": 0.20,
        },
    ),
    StrategyTemplate(
        id="tech_growth",
        name="科技成长型",
        level="高波动",
        positioning="显著提高纳斯达克100权重，追求长期成长弹性。",
        audience="适合投资期限长、能接受较大回撤、不会因阶段性深跌中断计划的人。",
        return_sources=["科技龙头盈利扩张", "创新周期", "高资本回报企业复利"],
        risks=["最大回撤可能显著高于其他策略", "估值收缩时下跌很快", "不适合短期资金"],
        weights={
            "china_large": 0.10,
            "china_mid": 0.10,
            "china_dividend": 0.05,
            "sp500": 0.35,
            "nasdaq100": 0.40,
        },
    ),
    StrategyTemplate(
        id="china_recovery",
        name="A股修复型",
        level="周期",
        positioning="提高A股宽基和红利权重，押注国内权益估值修复。",
        audience="适合看好A股中长期修复，愿意承受国内市场阶段性低迷的人。",
        return_sources=["低估值修复", "A股宽基盈利回升", "红利再投资", "中盘弹性"],
        risks=["修复时间可能很长", "政策和盈利周期影响大", "海外资产分散不足"],
        weights={
            "china_large": 0.35,
            "china_mid": 0.30,
            "china_dividend": 0.20,
            "sp500": 0.10,
            "nasdaq100": 0.05,
        },
    ),
]


def get_strategy(strategy_id: str) -> StrategyTemplate:
    for strategy in STRATEGIES:
        if strategy.id == strategy_id:
            return strategy
    return STRATEGIES[1]


def normalize_weights(weights: Dict[AssetKey, float]) -> Dict[AssetKey, float]:
    complete_weights = {key: max(float(weights.get(key, 0)), 0.0) for key in ASSET_NAMES.keys()}
    total = sum(complete_weights.values())
    if total <= 0:
        return get_strategy("balanced_compound").weights
    return {key: value / total for key, value in complete_weights.items()}


def build_personal_strategy(
    weights: Dict[AssetKey, float],
    name: str = "个人定制指数策略",
    positioning: str = "根据用户资金、风险偏好和投资周期生成的指数基金长期配置草案。",
    audience: str = "适合希望先确定长期配置，再按月执行纪律定投的普通投资者。",
    return_sources: List[str] | None = None,
    risks: List[str] | None = None,
) -> StrategyTemplate:
    return StrategyTemplate(
        id="personal_custom",
        name=name or "个人定制指数策略",
        level="个人",
        positioning=positioning,
        audience=audience,
        return_sources=return_sources
        or ["宽基指数长期盈利增长", "红利资产现金流再投资", "全球资产分散", "定投与再平衡纪律"],
        risks=risks
        or ["AI 只生成策略草案，不能保证收益", "指数基金仍会出现回撤", "跨境基金可能受汇率和溢价影响"],
        weights=normalize_weights(weights),
        is_personalized=True,
    )


def default_fund_pool() -> List[FundPoolItem]:
    strategy = get_strategy("balanced_compound")
    return [
        FundPoolItem(
            asset_key=key,
            index_name=ASSET_NAMES[key],
            target_weight=weight,
            asset_class=(
                "红利防守"
                if key == "china_dividend"
                else "海外宽基"
                if key in {"sp500", "nasdaq100"}
                else "A股宽基"
            ),
        )
        for key, weight in strategy.weights.items()
    ]
