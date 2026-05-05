"""共享 LLM 客户端:三 provider fallback (OpenRouter → OpenAI → Anthropic)

各 extractor 之前都内联了相同的 fallback 逻辑或只直连 Anthropic。
新写的 extractor 应该用 `call_llm` 统一入口。

使用方式:
    raw = await call_llm(
        db, prompt,
        max_tokens=2000,        # 默认 1500
        temperature=0.0,        # 默认 0
        prefer_haiku=True,      # Anthropic 走 haiku 模型(批量打分场景)
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
    """三 provider fallback,返回 raw 文本(可能为空字符串)"""

    async def _get(key: str) -> str:
        if db is not None:
            try:
                from app.services.settings_service import get_effective_value
                return await get_effective_value(db, key)
            except Exception:
                pass
        return str(getattr(app_settings, key, "") or "")

    # ── OpenRouter ────────────────────────────────────────────────
    try:
        or_key = await _get("openrouter_api_key")
        or_model = await _get("openrouter_model") or app_settings.openrouter_model
        if or_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
            resp = await client.chat.completions.create(
                model=or_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"[llm_client] OpenRouter 失败,尝试下一个: {e}")

    # ── OpenAI ────────────────────────────────────────────────────
    try:
        oai_key = await _get("openai_api_key")
        oai_model = await _get("openai_model") or app_settings.openai_model
        if oai_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=oai_key)
            resp = await client.chat.completions.create(
                model=oai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"[llm_client] OpenAI 失败,尝试下一个: {e}")

    # ── Anthropic ─────────────────────────────────────────────────
    try:
        ant_key = await _get("anthropic_api_key")
        if prefer_haiku:
            ant_model = (
                await _get("anthropic_haiku_model") or app_settings.anthropic_haiku_model
            )
        else:
            ant_model = await _get("anthropic_model") or app_settings.anthropic_model
        if ant_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=ant_key)
            resp = await client.messages.create(
                model=ant_model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
    except Exception as e:
        logger.error(f"[llm_client] Anthropic 失败: {e}")

    return ""
