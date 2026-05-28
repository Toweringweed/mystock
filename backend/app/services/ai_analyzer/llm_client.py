"""共享 LLM 客户端:四 provider fallback (DeepSeek → OpenRouter → OpenAI → Anthropic)

DeepSeek 直连价格最低,作为默认主入口。
可通过 .env 的 LLM_PROVIDER_PRIMARY 强制指定主入口(deepseek/openrouter/openai/anthropic)。

使用方式:
    raw = await call_llm(
        db, prompt,
        max_tokens=2000,        # 默认 1500
        temperature=0.0,        # 默认 0
        prefer_haiku=True,      # True = 用便宜快速模型(L1 批量打分);False = 用深度模型(L2)
    )
"""
import logging

from app.core.config import settings as app_settings

logger = logging.getLogger(__name__)


async def call_llm(
    db,
    prompt: str,
    *,
    max_tokens: int = 1500,
    temperature: float = 0.0,
    prefer_haiku: bool = False,
) -> str:
    """四 provider fallback,返回 raw 文本(可能为空字符串)"""

    async def _get(key: str) -> str:
        if db is not None:
            try:
                from app.services.settings_service import get_effective_value
                return await get_effective_value(db, key)
            except Exception:
                pass
        return str(getattr(app_settings, key, "") or "")

    primary = (await _get("llm_provider_primary")).lower().strip()

    providers = ["deepseek", "openrouter", "openai", "anthropic"]
    if primary in providers:
        providers.remove(primary)
        providers.insert(0, primary)

    for name in providers:
        try:
            if name == "deepseek":
                ds_key = await _get("deepseek_api_key")
                if not ds_key:
                    continue
                if prefer_haiku:
                    ds_model = await _get("deepseek_model") or app_settings.deepseek_model
                else:
                    ds_model = (
                        await _get("deepseek_deep_model")
                        or app_settings.deepseek_deep_model
                        or await _get("deepseek_model")
                        or app_settings.deepseek_model
                    )
                ds_base = await _get("deepseek_base_url") or app_settings.deepseek_base_url
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=ds_key, base_url=ds_base)
                resp = await client.chat.completions.create(
                    model=ds_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""

            elif name == "openrouter":
                or_key = await _get("openrouter_api_key")
                if not or_key:
                    continue
                or_model = await _get("openrouter_model") or app_settings.openrouter_model
                or_base = await _get("openrouter_base_url") or app_settings.openrouter_base_url
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=or_key, base_url=or_base)
                resp = await client.chat.completions.create(
                    model=or_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""

            elif name == "openai":
                oai_key = await _get("openai_api_key")
                if not oai_key:
                    continue
                oai_model = await _get("openai_model") or app_settings.openai_model
                oai_base = await _get("openai_base_url") or app_settings.openai_base_url
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=oai_key, base_url=oai_base)
                resp = await client.chat.completions.create(
                    model=oai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""

            elif name == "anthropic":
                ant_key = await _get("anthropic_api_key")
                if not ant_key:
                    continue
                if prefer_haiku:
                    ant_model = await _get("anthropic_haiku_model") or app_settings.anthropic_haiku_model
                else:
                    ant_model = await _get("anthropic_model") or app_settings.anthropic_model
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=ant_key)
                resp = await client.messages.create(
                    model=ant_model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text if resp.content else ""

        except Exception as e:
            logger.warning(f"[llm_client] {name} 失败,尝试下一个: {e}")

    return ""
