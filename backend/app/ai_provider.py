from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict

from .models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentToolTrace,
    AgentWorkbenchResponse,
    AIExplainResponse,
    AssetKey,
    DisciplineReviewResponse,
    HistoricalDataStatus,
    InvestmentRecord,
    MarketSnapshot,
    MonthlyPlan,
    PersonalStrategyRequest,
    PersonalStrategyResponse,
    Profile,
    ProviderConfigIn,
    ProviderConfigOut,
    StrategyTemplate,
)
from .strategies import ASSET_NAMES, build_personal_strategy


def mask_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"


def provider_out(config: ProviderConfigIn | None) -> ProviderConfigOut:
    config = config or ProviderConfigIn()
    return ProviderConfigOut(
        provider=config.provider,
        base_url=config.base_url,
        api_key_set=bool(config.api_key),
        api_key_mask=mask_key(config.api_key),
        model=config.model,
        temperature=config.temperature,
    )


def fallback_explanation(plan: MonthlyPlan) -> str:
    allocation_text = "；".join(
        f"{item.name} {item.amount:.0f} 元" for item in plan.allocations if item.amount > 0
    )
    if not allocation_text:
        allocation_text = "本月不新增买入，先守住现金安全垫"
    return (
        f"本月策略为「{plan.strategy_name}」，组合市场温度 {plan.average_temperature:.1f}，"
        f"处于「{plan.temperature_band}」区间。规则引擎给出的定投倍率是 {plan.multiplier:.2f}，"
        f"建议合计买入 {plan.suggested_total_buy:.0f} 元：{allocation_text}。"
        "这不是预测顶部或底部，而是在长期定投的基础上做节奏调节。"
        "执行时仍应保留应急现金，避免因为短期涨跌打乱长期计划。"
    )


def _call_chat(prompt: str, config: ProviderConfigIn, system: str) -> str:
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    url = config.base_url.rstrip("/") + "/v1/chat/completions"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def explain_with_provider(plan: MonthlyPlan, config: ProviderConfigIn | None) -> AIExplainResponse:
    if not config or not config.api_key:
        return AIExplainResponse(
            explanation=fallback_explanation(plan),
            provider_used="local-rule-explainer",
            fallback=True,
        )

    prompt = (
        "你是一个谨慎的指数基金定投教练。请解释以下规则引擎生成的月度计划。"
        "禁止承诺收益，禁止推荐个股，禁止覆盖规则金额。"
        "用中文，语气平静，结构为：结论、为什么、执行边界。\n\n"
        f"{plan.model_dump_json(indent=2)}"
    )
    try:
        content = _call_chat(prompt, config, "你只解释规则结果，不直接做投资决策。")
        return AIExplainResponse(
            explanation=content,
            provider_used=config.provider,
            fallback=False,
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError) as exc:
        return AIExplainResponse(
            explanation=fallback_explanation(plan) + f"\n\nAI 暂不可用，已使用本地解释。错误摘要：{exc}",
            provider_used="local-rule-explainer",
            fallback=True,
        )


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def _coerce_weights(raw_weights: dict | None) -> Dict[AssetKey, float]:
    raw_weights = raw_weights or {}
    weights: Dict[AssetKey, float] = {}
    for asset_key in ASSET_NAMES.keys():
        try:
            weights[asset_key] = float(raw_weights.get(asset_key, 0))
        except (TypeError, ValueError):
            weights[asset_key] = 0
    return weights


def _fallback_personal_strategy(request: PersonalStrategyRequest, reason: str = "") -> PersonalStrategyResponse:
    preference = request.profile.risk_preference
    if preference == "conservative":
        name = "个人稳健红利策略"
        weights: Dict[AssetKey, float] = {
            "china_large": 0.18,
            "china_mid": 0.12,
            "china_dividend": 0.35,
            "sp500": 0.25,
            "nasdaq100": 0.10,
        }
        positioning = "以红利和全球宽基为核心，优先控制持有体验和回撤压力。"
    elif preference == "growth":
        name = "个人成长复利策略"
        weights = {
            "china_large": 0.15,
            "china_mid": 0.15,
            "china_dividend": 0.10,
            "sp500": 0.35,
            "nasdaq100": 0.25,
        }
        positioning = "提高美股和科技成长权重，追求长期复利弹性，但接受更深波动。"
    else:
        name = "个人均衡复利策略"
        weights = {
            "china_large": 0.20,
            "china_mid": 0.20,
            "china_dividend": 0.15,
            "sp500": 0.30,
            "nasdaq100": 0.15,
        }
        positioning = "在A股宽基、红利、美股宽基和科技成长之间做均衡分散。"

    strategy = build_personal_strategy(
        weights=weights,
        name=name,
        positioning=positioning,
        audience="适合希望先确定长期资产配置，再按月执行纪律定投的投资者。",
    )
    suffix = f" 原因：{reason}" if reason else ""
    return PersonalStrategyResponse(
        strategy=strategy,
        explanation=(
            "当前使用本地策略顾问生成个人策略草案。它根据风险偏好选择保守、均衡或成长配置，"
            "后续月度买入金额仍由市场温度和现金池规则计算。"
            f"{suffix}"
        ),
        provider_used="local-strategy-advisor",
        fallback=True,
    )


def generate_personal_strategy(
    request: PersonalStrategyRequest,
    config: ProviderConfigIn | None,
) -> PersonalStrategyResponse:
    if not config or not config.api_key:
        return _fallback_personal_strategy(request)

    prompt = (
        "你是一个谨慎的指数基金长期配置顾问。请根据用户资料生成一个只包含指数基金类别的长期配置草案。"
        "约束：不推荐个股，不推荐主动基金，不承诺收益，不做短期择时。"
        "权重只能使用以下五个键，且总和接近 1：china_large、china_mid、china_dividend、sp500、nasdaq100。"
        "请只输出 JSON，不要输出 Markdown。JSON 格式如下："
        '{"name":"...","positioning":"...","audience":"...","weights":{"china_large":0.2,'
        '"china_mid":0.2,"china_dividend":0.15,"sp500":0.3,"nasdaq100":0.15},'
        '"return_sources":["..."],"risks":["..."],"explanation":"..."}'
        "\n\n用户资料：\n"
        f"{request.model_dump_json(indent=2)}"
    )

    try:
        content = _call_chat(
            prompt,
            config,
            "你只生成长期指数基金配置草案。所有金额和买卖动作由规则引擎决定。",
        )
        payload = _extract_json(content)
        strategy = build_personal_strategy(
            weights=_coerce_weights(payload.get("weights")),
            name=str(payload.get("name") or "个人定制指数策略"),
            positioning=str(payload.get("positioning") or "根据用户资料生成的长期指数基金配置草案。"),
            audience=str(payload.get("audience") or "适合按月执行纪律定投的普通投资者。"),
            return_sources=[str(item) for item in payload.get("return_sources", [])],
            risks=[str(item) for item in payload.get("risks", [])],
        )
        explanation = str(payload.get("explanation") or content)
        return PersonalStrategyResponse(
            strategy=strategy,
            explanation=explanation,
            provider_used=config.provider,
            fallback=False,
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
        return _fallback_personal_strategy(request, reason=f"DeepSeek 暂不可用或返回格式无法解析：{exc}")


def build_agent_tools(
    profile: Profile,
    strategy: StrategyTemplate,
    market: MarketSnapshot,
    plan: MonthlyPlan,
    history: HistoricalDataStatus,
    records: list[InvestmentRecord],
) -> list[AgentToolTrace]:
    live_assets = [asset for asset in market.assets if asset.is_live]
    history_ready = [source for source in history.sources if source.row_count > 0]
    executed = [record for record in records if record.executed]
    pending = [record for record in records if not record.executed]
    return [
        AgentToolTrace(
            name="读取用户画像",
            status="done",
            summary="已读取资金、现金安全垫、风险偏好和计划投完时间。",
            evidence=[
                f"一次性待投资金 {profile.lump_sum_capital:.0f} 元",
                f"每月可投 {profile.monthly_contribution:.0f} 元",
                f"应急现金底线 {profile.emergency_cash_floor:.0f} 元",
            ],
        ),
        AgentToolTrace(
            name="读取当前策略",
            status="done" if strategy.is_personalized else "warning",
            summary="当前策略会决定资产权重；如果仍是模板策略，建议先生成个人策略。",
            evidence=[
                f"{strategy.name}；{'个人策略' if strategy.is_personalized else '模板策略'}",
                " / ".join(f"{ASSET_NAMES[key]} {weight:.0%}" for key, weight in strategy.weights.items()),
            ],
        ),
        AgentToolTrace(
            name="评估每日市场温度",
            status="done" if live_assets else "warning",
            summary="已读取各指数价格、均线、回撤和波动；估值分位仍是后续增强项。",
            evidence=[
                f"{len(live_assets)}/{len(market.assets)} 个指数使用真实K线",
                f"组合温度 {plan.average_temperature:.1f}，处于{plan.temperature_band}",
                f"数据标签：{market.data_quality}",
            ],
        ),
        AgentToolTrace(
            name="调用纪律计划规则",
            status="done",
            summary="买入金额由规则引擎生成，AI 不直接改金额。",
            evidence=[
                f"基础月投入 {plan.base_amount:.0f} 元",
                f"温度倍率 {plan.multiplier:.2f}",
                f"本期建议买入 {plan.suggested_total_buy:.0f} 元",
            ],
        ),
        AgentToolTrace(
            name="检查历史回测数据",
            status="done" if len(history_ready) == len(history.sources) else "warning",
            summary="回测数据缺口会显式展示，不静默补齐。",
            evidence=[
                f"{len(history_ready)}/{len(history.sources)} 类资产已有历史缓存",
                f"历史数据状态：{history.data_quality}",
            ],
        ),
        AgentToolTrace(
            name="读取投资记录",
            status="done" if records else "warning",
            summary="投资记录用于复盘是否执行纪律；没有记录时只能给计划，不能复盘行为。",
            evidence=[
                f"总记录 {len(records)} 条",
                f"已执行 {len(executed)} 条，待执行 {len(pending)} 条",
            ],
        ),
    ]


def _market_focus(market: MarketSnapshot) -> list[str]:
    sorted_assets = sorted(market.assets, key=lambda asset: asset.temperature)
    cold = sorted_assets[:2]
    hot = sorted_assets[-2:]
    focus = [f"{asset.name}温度 {asset.temperature:.0f}，偏低时优先观察定投机会。" for asset in cold]
    focus.extend(f"{asset.name}温度 {asset.temperature:.0f}，偏热时避免额外追涨。" for asset in hot)
    return focus[:4]


def _missing_data(market: MarketSnapshot, history: HistoricalDataStatus) -> list[str]:
    missing: list[str] = []
    if not all(asset.is_live for asset in market.assets):
        missing.append("部分指数未取得真实K线，当前市场温度可能使用代理或兜底数据。")
    if "NO_VALUATION" in market.data_quality or "VALUATION" in market.data_quality:
        missing.append("估值分位、股息率分位尚未完整接入，市场温度主要来自价格、均线、回撤和波动。")
    for source in history.sources:
        if source.row_count <= 0:
            missing.append(f"{source.name}暂无可用历史缓存，相关回测会降级或提示数据不足。")
    return missing[:6]


def fallback_agent_workbench(
    profile: Profile,
    strategy: StrategyTemplate,
    market: MarketSnapshot,
    plan: MonthlyPlan,
    history: HistoricalDataStatus,
    records: list[InvestmentRecord],
) -> AgentWorkbenchResponse:
    tools = build_agent_tools(profile, strategy, market, plan, history, records)
    if profile.current_cash <= profile.emergency_cash_floor:
        headline = "先守住现金安全垫，本期暂停新增买入。"
    elif not strategy.is_personalized:
        headline = "当前仍是模板策略，建议先生成个人纪律书。"
    else:
        headline = f"当前个人策略可执行，本期按 {plan.multiplier:.2f} 倍纪律买入。"
    next_actions = [
        "先在“我的策略”确认或生成个人策略。",
        f"本期按规则买入 {plan.suggested_total_buy:.0f} 元，并按策略权重拆分。",
        "执行后保存到投资记录，月底再复盘是否遵守纪律。",
    ]
    return AgentWorkbenchResponse(
        generated_at=plan.generated_at,
        provider_used="local-agent-orchestrator",
        fallback=True,
        headline=headline,
        brief=(
            f"Agent 已读取用户画像、当前策略、每日市场温度、历史数据状态和投资记录。"
            f"当前策略为{strategy.name}，组合温度{plan.average_temperature:.1f}，"
            f"建议买入{plan.suggested_total_buy:.0f}元。AI 负责解释和追问，金额由规则引擎生成。"
        ),
        tools=tools,
        next_actions=next_actions,
        missing_data=_missing_data(market, history),
        suggested_questions=[
            "为什么这次不是一次性买完？",
            "我的策略和均衡复利型相比差在哪里？",
            "如果这个月不执行，会破坏长期计划吗？",
            "当前最需要关注哪几个指数？",
        ],
    )


def summarize_agent_workbench(
    profile: Profile,
    strategy: StrategyTemplate,
    market: MarketSnapshot,
    plan: MonthlyPlan,
    history: HistoricalDataStatus,
    records: list[InvestmentRecord],
    config: ProviderConfigIn | None,
) -> AgentWorkbenchResponse:
    fallback = fallback_agent_workbench(profile, strategy, market, plan, history, records)
    if not config or not config.api_key:
        return fallback

    context = {
        "profile": profile.model_dump(mode="json"),
        "strategy": strategy.model_dump(mode="json"),
        "market": market.model_dump(mode="json"),
        "monthly_plan": plan.model_dump(mode="json"),
        "history_status": history.model_dump(mode="json"),
        "record_count": len(records),
        "executed_record_count": len([record for record in records if record.executed]),
    }
    prompt = (
        "你是一个指数基金被动收益 Agent 的总控台。你不能直接决定买卖金额，金额必须尊重规则引擎结果。"
        "请基于上下文输出一个面向普通用户的今日工作台摘要，强调你读取了哪些工具、哪些数据不足、下一步做什么。"
        "只输出 JSON："
        '{"headline":"...","brief":"...","next_actions":["..."],"suggested_questions":["..."]}'
        "\n\n上下文：\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
    try:
        payload = _extract_json(
            _call_chat(
                prompt,
                config,
                "你是长期指数基金纪律顾问，只解释工具和规则结果，不承诺收益，不推荐个股，不自动下单。",
            )
        )
        return fallback.model_copy(
            update={
                "provider_used": config.provider,
                "fallback": False,
                "headline": str(payload.get("headline") or fallback.headline),
                "brief": str(payload.get("brief") or fallback.brief),
                "next_actions": [str(item) for item in payload.get("next_actions", fallback.next_actions)][:5],
                "suggested_questions": [
                    str(item) for item in payload.get("suggested_questions", fallback.suggested_questions)
                ][:5],
            }
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, ValueError):
        return fallback


def fallback_agent_chat(request: AgentChatRequest, tools: list[AgentToolTrace]) -> AgentChatResponse:
    question = request.question.strip()
    plan = request.plan
    strategy = request.strategy
    market = request.market
    if "回测" in question or "历史" in question or "收益" in question:
        answer = (
            "回测会优先使用本地历史行情缓存；如果某类资产缺数据，页面会展示数据质量标签，不会静默补齐。"
            "个人策略生成后也会作为 custom_weights 调用同一套回测引擎，所以能和模板策略放在同一个口径下比较。"
        )
    elif "买" in question or "卖" in question or "行动" in question:
        if plan:
            answer = (
                f"按当前规则，本期建议买入 {plan.suggested_total_buy:.0f} 元，组合温度 {plan.average_temperature:.1f}"
                f"（{plan.temperature_band}），倍率 {plan.multiplier:.2f}。"
                "如果没有录入持仓，Agent 不会编造卖出金额；卖出只在极热且严重超配时作为复核提醒。"
            )
        else:
            answer = "当前还没有月度计划，请先生成个人策略或刷新行动指南。"
    elif "策略" in question or "个人" in question:
        if strategy:
            answer = (
                f"当前策略是{strategy.name}。"
                f"{'它是个人策略，已进入首页、行动指南和回测。' if strategy.is_personalized else '它仍是模板策略，建议到“我的策略”生成个人纪律书。'}"
                "AI 负责把你的目标、风险承受和偏好翻译成长期权重，规则引擎负责后续每月金额。"
            )
        else:
            answer = "当前未读取到策略，请先选择模板或生成个人策略。"
    elif "市场" in question or "温度" in question or "指数" in question:
        if market:
            answer = "今日关注：" + "；".join(_market_focus(market))
        else:
            answer = "当前未读取到市场快照，请先刷新每日评估。"
    elif "记录" in question or "复盘" in question or "执行" in question:
        executed = len([record for record in request.records if record.executed])
        answer = (
            f"当前投资记录共 {len(request.records)} 条，其中 {executed} 条已执行。"
            "记录的价值不是后悔，而是复盘有没有偏离纪律；后续 Agent 会根据记录提醒你是否追涨、停投或重复保存。"
        )
    else:
        answer = (
            "我会围绕你的个人策略、市场温度、现金池、行动指南和投资记录回答。"
            "关键边界是：AI 可以解释和追问，不能覆盖规则金额，也不承诺收益。"
        )
    return AgentChatResponse(
        answer=answer,
        provider_used="local-agent-chat",
        fallback=True,
        tools=tools,
        suggested_questions=[
            "我这个月到底该买多少？",
            "当前哪个指数更值得关注？",
            "我的个人策略会不会太激进？",
            "这次建议应该保存到投资记录吗？",
        ],
    )


def chat_with_agent(request: AgentChatRequest, config: ProviderConfigIn | None) -> AgentChatResponse:
    profile = request.profile or Profile()
    strategy = request.strategy or build_personal_strategy(weights={})
    market = request.market
    plan = request.plan
    tools = [
        AgentToolTrace(
            name="读取当前上下文",
            status="done",
            summary="已读取用户画像、策略、市场快照、月度计划和投资记录。",
            evidence=[
                f"策略：{strategy.name}",
                f"计划：{plan.suggested_total_buy:.0f} 元" if plan else "计划：未生成",
                f"记录：{len(request.records)} 条",
            ],
        )
    ]
    fallback = fallback_agent_chat(request, tools)
    if not config or not config.api_key:
        return fallback

    context = {
        "profile": profile.model_dump(mode="json"),
        "strategy": strategy.model_dump(mode="json"),
        "market": market.model_dump(mode="json") if market else None,
        "monthly_plan": plan.model_dump(mode="json") if plan else None,
        "records": [record.model_dump(mode="json") for record in request.records[:8]],
    }
    prompt = (
        "你是被动收益 Agent 的对话副驾驶。回答必须基于给定上下文；不能推荐个股，不能承诺收益，不能擅自改变规则金额。"
        "如果数据不足，要明确说缺什么。请用中文，先给结论，再给依据和边界。"
        "\n\n用户问题：\n"
        f"{request.question}\n\n上下文：\n"
        f"{json.dumps(context, ensure_ascii=False)}"
    )
    try:
        content = _call_chat(
            prompt,
            config,
            "你是长期指数基金纪律顾问。规则金额不可覆盖；不自动下单；不推荐个股或主动基金。",
        )
        return AgentChatResponse(
            answer=content,
            provider_used=config.provider,
            fallback=False,
            tools=tools,
            suggested_questions=fallback.suggested_questions,
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
        return fallback.model_copy(
            update={
                "answer": fallback.answer + f"\n\n模型暂时不可用，已使用本地上下文回答。错误摘要：{exc}",
            }
        )


def review_discipline(records: list[InvestmentRecord], config: ProviderConfigIn | None) -> DisciplineReviewResponse:
    total = len(records)
    executed = len([record for record in records if record.executed])
    pending = total - executed
    score = 50 if total == 0 else round(100 * executed / total)
    observations = [
        f"已保存 {total} 条建议，其中 {executed} 条标记已执行，{pending} 条仍待执行。",
        "复盘只评价纪律执行，不评价短期涨跌对错。",
    ]
    next_actions = [
        "把最近一条建议标记为已执行或待执行。",
        "如果连续多期未执行，回到我的策略页降低波动或减少计划金额。",
    ]
    fallback = DisciplineReviewResponse(
        generated_at=records[0].created_at if records else datetime.utcnow(),
        provider_used="local-discipline-review",
        fallback=True,
        score=score,
        summary="当前复盘基于投资记录的执行状态生成。记录越完整，Agent 越能发现你是否偏离纪律。",
        observations=observations,
        next_actions=next_actions,
    )
    if not config or not config.api_key or not records:
        return fallback

    prompt = (
        "你是指数基金定投纪律复盘助手。只评价执行纪律，不评价短期行情对错。"
        "输出 JSON："
        '{"score":80,"summary":"...","observations":["..."],"next_actions":["..."]}'
        "\n\n投资记录：\n"
        f"{json.dumps([record.model_dump(mode='json') for record in records[:20]], ensure_ascii=False)}"
    )
    try:
        payload = _extract_json(
            _call_chat(prompt, config, "你只做纪律复盘，不做收益承诺，不推荐交易。")
        )
        return fallback.model_copy(
            update={
                "provider_used": config.provider,
                "fallback": False,
                "score": max(0, min(100, int(payload.get("score", score)))),
                "summary": str(payload.get("summary") or fallback.summary),
                "observations": [str(item) for item in payload.get("observations", observations)][:6],
                "next_actions": [str(item) for item in payload.get("next_actions", next_actions)][:5],
            }
        )
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError, ValueError):
        return fallback
