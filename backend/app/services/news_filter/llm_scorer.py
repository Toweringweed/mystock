"""LLM 打分器（Claude Haiku 批量）

输入：候选新闻列表（每条带 stock 候选与基础信息）
输出：每条的 direction / strength / sentiment / summary / per-stock relevance 修正

走 ai_analyzer.llm_client.call_llm 统一 provider fallback (DeepSeek → OpenRouter → OpenAI → Anthropic)，
prefer_haiku=True 让 Anthropic 路径使用 haiku 模型。
"""
import json
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BATCH_SIZE = 8
MAX_TOKENS = 2000


@dataclass
class LLMNewsInput:
    idx: int               # 输入序号（用于回填）
    title: str
    content: str | None
    source: str
    candidate_stocks: dict[int, str]  # {stock_id: stock_name}


@dataclass
class LLMNewsOutput:
    idx: int
    direction: str         # bullish / bearish / neutral
    strength: int          # 1~5
    sentiment: str         # positive / negative / neutral
    summary: str           # 100 字摘要
    stock_relevance: dict[int, float]  # 每只候选股的相关度修正 0~1


PROMPT_TEMPLATE = """你是资深A股/港股投资分析师。下面是 {n} 条待打分的资讯（编号 0~{last}），请逐条分析其对相关股票的影响。

待分析资讯：
{news_block}

请输出 JSON（不要有任何多余文字），格式如下：
{{
  "results": [
    {{
      "idx": 0,
      "direction": "bullish|bearish|neutral",
      "strength": 1,
      "sentiment": "positive|negative|neutral",
      "summary": "100字以内的中文摘要",
      "stock_relevance": {{"<stock_id>": 0.85, "<stock_id>": 0.20}}
    }}
  ]
}}

字段说明：
- direction：对相关股票短期股价的影响方向
- strength：1=噪音/无影响，3=中等关注，5=高确定性大幅影响
- sentiment：资讯本身的情感色彩
- summary：核心要点，避免套话，包含关键数字
- stock_relevance：每只候选股的真实相关度 0~1（基于资讯实际是否提到、影响多大）
"""


def _format_news_block(items: list[LLMNewsInput]) -> str:
    blocks = []
    for it in items:
        candidates = ", ".join(
            f'"{sid}":"{name}"' for sid, name in it.candidate_stocks.items()
        ) or "（无）"
        content_preview = (it.content or "")[:300]
        blocks.append(
            f"[{it.idx}] 来源={it.source} | 候选股={{{candidates}}}\n"
            f"标题：{it.title}\n"
            f"内容片段：{content_preview}"
        )
    return "\n\n".join(blocks)


def _parse_response(raw: str) -> list[LLMNewsOutput]:
    if not raw:
        return []
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        data = json.loads(raw[start:end])
    except Exception as e:
        logger.warning(f"[llm_scorer] JSON 解析失败: {e}")
        return []

    out: list[LLMNewsOutput] = []
    for r in data.get("results", []):
        try:
            stock_rel_raw = r.get("stock_relevance") or {}
            stock_rel = {int(k): float(v) for k, v in stock_rel_raw.items()}
            out.append(
                LLMNewsOutput(
                    idx=int(r["idx"]),
                    direction=str(r.get("direction", "neutral")),
                    strength=int(r.get("strength", 1)),
                    sentiment=str(r.get("sentiment", "neutral")),
                    summary=str(r.get("summary", ""))[:200],
                    stock_relevance=stock_rel,
                )
            )
        except Exception as e:
            logger.debug(f"[llm_scorer] 单条结果解析失败: {e}")
    return out


async def score_batch(
    db: AsyncSession, items: list[LLMNewsInput]
) -> list[LLMNewsOutput]:
    """批量打分（一次调用最多 BATCH_SIZE 条）"""
    if not items:
        return []

    from app.services.ai_analyzer.llm_client import call_llm

    out: list[LLMNewsOutput] = []
    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i : i + BATCH_SIZE]
        prompt = PROMPT_TEMPLATE.format(
            n=len(chunk),
            last=len(chunk) - 1,
            news_block=_format_news_block(chunk),
        )
        try:
            raw = await call_llm(
                db,
                prompt,
                max_tokens=MAX_TOKENS,
                prefer_haiku=True,
            )
        except Exception as e:
            logger.error(f"[llm_scorer] LLM 调用失败: {e}")
            continue

        if not raw:
            logger.warning("[llm_scorer] LLM 返回空，跳过该批")
            continue

        parsed = _parse_response(raw)
        out.extend(parsed)

    return out
