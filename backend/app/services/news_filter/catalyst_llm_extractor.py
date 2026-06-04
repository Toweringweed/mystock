"""L1.5 — DeepSeek 一次调用抽取 catalyst_summary + key_risks

设计:
- 比 L0 规则深(给出文字描述),比 L2 深度分析浅(只 2 个字段)
- 单次 DeepSeek-chat 调用,prompt 紧凑,max_tokens=200
- 输出严格 JSON,容错解析
- 失败时返回 (None, None) — 不阻塞主流水线

入口:extract_catalyst_and_risks(db, title, content, catalyst_type) -> (summary, risks)
"""
from __future__ import annotations

import json
import logging
import re

from app.services.ai_analyzer.llm_client import call_llm
from app.services.news_filter.catalyst_extractor import CATALYST_LABELS_ZH

logger = logging.getLogger(__name__)


_PROMPT_TEMPLATE = """你是 A 股资讯催化剂分析助手。从下面的资讯中提取两个字段:

1. catalyst_summary: 用一句话(<=40 字)总结这条新闻对股价的核心催化逻辑。聚焦"为什么会影响股价",不要复述新闻原文。
2. key_risks: 1-3 条关键风险(每条 <=30 字),用 / 分隔。如果新闻完全是利好且无明显风险,填 "暂无明显风险"。

L0 规则识别的催化剂类别(参考): {catalyst_label}

新闻标题: {title}
新闻摘要/正文(节选): {body}

仅输出严格 JSON,无任何解释:
{{"catalyst_summary": "...", "key_risks": "..."}}
"""


_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


async def extract_catalyst_and_risks(
    db,
    *,
    title: str,
    content: str | None = None,
    summary: str | None = None,
    catalyst_type: str = "other",
) -> tuple[str | None, str | None]:
    """返回 (catalyst_summary, key_risks);任何失败均返回 (None, None)。"""
    if not title:
        return None, None

    body = (summary or content or "")[:600]
    label = CATALYST_LABELS_ZH.get(catalyst_type, "其他")
    prompt = _PROMPT_TEMPLATE.format(
        catalyst_label=label,
        title=title.strip(),
        body=body.strip(),
    )

    try:
        raw = await call_llm(
            db,
            prompt,
            max_tokens=200,
            temperature=0.1,
            prefer_haiku=True,  # 用 deepseek-chat (L1 快速便宜)
        )
    except Exception as e:
        logger.warning(f"[L1.5] LLM 调用失败 title={title[:30]!r}: {e}")
        return None, None

    if not raw:
        return None, None

    # 容错 JSON 解析:抓首个 {...}
    match = _JSON_RE.search(raw)
    if not match:
        logger.debug(f"[L1.5] 未找到 JSON 块 raw={raw[:120]!r}")
        return None, None

    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.debug(f"[L1.5] JSON 解析失败 raw={raw[:120]!r}")
        return None, None

    cs = (obj.get("catalyst_summary") or "").strip() or None
    kr = (obj.get("key_risks") or "").strip() or None

    # 长度截断,与 DB 列长度对齐
    if cs and len(cs) > 120:
        cs = cs[:117] + "..."
    if kr and len(kr) > 240:
        kr = kr[:237] + "..."

    return cs, kr
