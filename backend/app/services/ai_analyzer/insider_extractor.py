"""减持/增持公告标题 LLM 结构化提取（Haiku 批量）

输入：公告标题（必要时含正文片段）
输出：trade_type / holder_name / shares / pct_of_total / price_range
"""
import json
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.services.settings_service import get_effective_value

logger = logging.getLogger(__name__)

BATCH_SIZE = 10


@dataclass
class InsiderInput:
    idx: int
    code: str
    title: str
    content: str | None
    ann_date: str  # ISO date


@dataclass
class InsiderOutput:
    idx: int
    is_insider: bool
    trade_type: str | None  # reduce / increase
    holder_name: str | None
    shares: int | None
    pct_of_total: float | None
    price_low: float | None
    price_high: float | None


PROMPT = """下面是 {n} 条公司公告标题，可能涉及股东减持/增持/回购。逐条判断并提取结构化数据。

公告：
{block}

输出 JSON（无任何多余文字）：
{{
  "results": [
    {{
      "idx": 0,
      "is_insider": true,
      "trade_type": "reduce|increase",
      "holder_name": "股东全称",
      "shares": 1234567,
      "pct_of_total": 1.23,
      "price_low": 10.5,
      "price_high": 11.2
    }}
  ]
}}

字段说明：
- is_insider=false 表示非减持/增持类（如纯回购计划公告，但已实施回购仍算 increase）
- trade_type 只能是 reduce 或 increase
- shares: 实际/计划交易股数（无信息留 null）
- pct_of_total: 占总股本百分比（如"占总股本 1.23%"则填 1.23；不是 0.0123）
- price_low/high: 交易价格区间，无信息留 null
- 如标题不含具体数字，仅设置 is_insider 与 trade_type，其他字段留 null
"""


def _parse(raw: str) -> list[dict]:
    if not raw:
        return []
    try:
        s = raw.find("{")
        e = raw.rfind("}") + 1
        if s < 0 or e <= s:
            return []
        return json.loads(raw[s:e]).get("results", [])
    except Exception as e:
        logger.warning(f"[insider_extractor] JSON 解析失败: {e}")
        return []


async def extract_batch(
    db: AsyncSession, items: list[InsiderInput]
) -> list[InsiderOutput]:
    if not items:
        return []

    from app.services.ai_analyzer.llm_client import call_llm
    out: list[InsiderOutput] = []

    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i : i + BATCH_SIZE]
        block = "\n".join(
            f"[{it.idx}] {it.code} {it.ann_date} | 标题：{it.title}"
            + (f"\n     片段：{(it.content or '')[:200]}" if it.content else "")
            for it in chunk
        )
        prompt = PROMPT.format(n=len(chunk), block=block)
        try:
            raw = await call_llm(db, prompt, max_tokens=1500, prefer_haiku=True)
        except Exception as e:
            logger.error(f"[insider_extractor] LLM 调用失败: {e}")
            continue
        for r in _parse(raw):
            try:
                out.append(InsiderOutput(
                    idx=int(r["idx"]),
                    is_insider=bool(r.get("is_insider")),
                    trade_type=r.get("trade_type"),
                    holder_name=r.get("holder_name"),
                    shares=int(r["shares"]) if r.get("shares") is not None else None,
                    pct_of_total=float(r["pct_of_total"]) if r.get("pct_of_total") is not None else None,
                    price_low=float(r["price_low"]) if r.get("price_low") is not None else None,
                    price_high=float(r["price_high"]) if r.get("price_high") is not None else None,
                ))
            except Exception as e:
                logger.debug(f"[insider_extractor] 单条结果解析失败: {e}")
    return out
