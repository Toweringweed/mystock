"""英文资讯标题 + 摘要翻译为中文,保留原文。

设计:
- 仅当 detect_lang() 返回 "en" 时调用 LLM
- 标题 + 摘要一次性合并翻译(单次 LLM 调用降本)
- Redis 缓存 24h(相同英文文本不重复调)
- LLM 失败 → 返回原文(不阻塞)

入口:
    title_zh, summary_zh, lang = await translate_if_needed(db, title, summary)
    # 若英文: 返回中文翻译 + lang="en"
    # 若中文: 返回原文 + lang="zh"

caller 应将 original_title=title (原英文), title=title_zh (中文)写入 DB。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Optional

from app.core.config import settings as app_settings
from app.services.ai_analyzer.llm_client import call_llm

logger = logging.getLogger(__name__)


_REDIS_TTL_SEC = 60 * 60 * 24
_PROMPT_TEMPLATE = """将下面的英文财经新闻翻译成简体中文,要求:
1. 标题翻译要简洁、专业、符合 A 股财经媒体语境
2. 摘要保持原意,精炼到 100 字以内
3. 公司名/股票代码保留英文(如 NVIDIA / TSMC / 0700.HK)
4. 仅输出严格 JSON, 无任何额外说明

英文标题: {title}
英文摘要: {summary}

输出格式:
{{"title_zh": "...", "summary_zh": "..."}}
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def detect_lang(text: str) -> str:
    """极简语言检测 — 中文字符占比 > 20% 算 zh,否则 en。"""
    if not text:
        return "zh"
    chinese = sum(1 for ch in text if "一" <= ch <= "鿿")
    return "zh" if chinese / max(len(text), 1) > 0.2 else "en"


def _cache_key(title: str, summary: str) -> str:
    h = hashlib.sha1(f"{title}|||{summary}".encode("utf-8")).hexdigest()[:16]
    return f"news:tr:{h}"


async def _redis_get(key: str) -> Optional[str]:
    try:
        from redis.asyncio import Redis
        client = Redis.from_url(app_settings.redis_url, decode_responses=True)
        try:
            return await client.get(key)
        finally:
            await client.aclose()
    except Exception as e:
        logger.debug(f"[translator] redis get fail {e}")
        return None


async def _redis_set(key: str, value: str) -> None:
    try:
        from redis.asyncio import Redis
        client = Redis.from_url(app_settings.redis_url, decode_responses=True)
        try:
            await client.set(key, value, ex=_REDIS_TTL_SEC)
        finally:
            await client.aclose()
    except Exception as e:
        logger.debug(f"[translator] redis set fail {e}")


async def translate_if_needed(
    db,
    *,
    title: str,
    summary: str | None = None,
) -> tuple[str, str, str]:
    """如果英文则翻译,否则原样返回。

    返回 (title_out, summary_out, lang)
    - title_out / summary_out:中文(英文翻译过来)或原文(本就是中文)
    - lang:"en" 或 "zh"
    """
    summary = summary or ""
    title_lang = detect_lang(title)

    if title_lang == "zh":
        return title, summary, "zh"

    # 命中缓存
    cache_k = _cache_key(title, summary)
    cached = await _redis_get(cache_k)
    if cached:
        try:
            obj = json.loads(cached)
            return obj["title_zh"], obj.get("summary_zh", ""), "en"
        except Exception:
            pass

    # 调 LLM
    prompt = _PROMPT_TEMPLATE.format(
        title=title.strip(),
        summary=summary.strip()[:500],
    )
    try:
        raw = await call_llm(db, prompt, max_tokens=300, temperature=0.0, prefer_haiku=True)
    except Exception as e:
        logger.warning(f"[translator] LLM 调用失败 title={title[:30]!r}: {e}")
        return title, summary, "en"

    if not raw:
        return title, summary, "en"

    match = _JSON_RE.search(raw)
    if not match:
        return title, summary, "en"
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return title, summary, "en"

    title_zh = (obj.get("title_zh") or "").strip() or title
    summary_zh = (obj.get("summary_zh") or "").strip() or summary

    # 写缓存
    await _redis_set(cache_k, json.dumps({"title_zh": title_zh, "summary_zh": summary_zh}))

    return title_zh, summary_zh, "en"
