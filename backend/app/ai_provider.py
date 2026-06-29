from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Dict

from .models import (
    AIExplainResponse,
    AssetKey,
    MonthlyPlan,
    PersonalStrategyRequest,
    PersonalStrategyResponse,
    ProviderConfigIn,
    ProviderConfigOut,
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
