"""股票标签 AI 提取器

输入：公司基础信息（名称 / 行业 / 业务板块 / 上下游）
输出：3~8 个标签 [{name, category, confidence}]，类别为 theme / industry_chain / attribute

走 ai_analyzer.llm_client.call_llm 统一 fallback (OpenRouter → OpenAI → Anthropic)。
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_segment import BusinessSegment
from app.models.stock import Stock
from app.models.supply_chain import SupplyChain
from app.services.ai_analyzer.llm_client import call_llm

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {"theme", "industry_chain", "attribute"}


PROMPT = """你是 A 股/港股研究员。请根据下列公司信息，为该公司生成 3~8 个核心特征标签，反映其投资主题、产业链定位与企业属性。

公司：{name}（{code}）
行业：{industry}
业务板块：{segments}
上游：{upstream}
下游：{downstream}

要求：
1. 每个标签必须属于以下类别之一：
   - theme（主题/题材）：例如 国产替代、人工智能、新能源、AI算力
   - industry_chain（产业链联盟）：例如 英伟达链、苹果链、华为链、特斯拉链
   - attribute（企业属性）：例如 央企、次新股、高股息、北交所
2. 标签名 ≤ 8 字，不含 # 号
3. confidence 取 0~1，反映把握度（核心特征 0.8+；猜测性 0.5 左右）
4. 优先生成有信息量、能区分公司的标签，避免太宽泛（如"科技股"）

输出 JSON（不要多余文字）：
{{"tags":[{{"name":"国产替代","category":"theme","confidence":0.9}},{{"name":"英伟达链","category":"industry_chain","confidence":0.85}}]}}
"""


class TagsExtractor:
    async def extract(
        self, db: AsyncSession, stock: Stock
    ) -> list[dict]:
        ctx = await self._build_context(db, stock)
        prompt = PROMPT.format(**ctx)
        try:
            raw = await call_llm(db, prompt, max_tokens=1000, prefer_haiku=True)
        except Exception as e:
            logger.error(f"[tags_extractor] [{stock.code}] LLM 调用失败: {e}")
            return []
        return self._parse(raw)

    async def _build_context(
        self, db: AsyncSession, stock: Stock
    ) -> dict:
        # 业务板块
        seg_res = await db.execute(
            select(BusinessSegment.segment_name, BusinessSegment.revenue_pct)
            .where(BusinessSegment.stock_id == stock.id)
            .order_by(BusinessSegment.revenue_pct.desc().nullslast())
            .limit(8)
        )
        segments_parts: list[str] = []
        for name, pct in seg_res.all():
            if pct is not None:
                segments_parts.append(f"{name}({float(pct) * 100:.0f}%)")
            else:
                segments_parts.append(str(name))
        segments = "、".join(segments_parts) if segments_parts else "（无）"

        # 上下游
        sc_res = await db.execute(
            select(SupplyChain.relation_type, SupplyChain.company_name)
            .where(SupplyChain.stock_id == stock.id)
            .order_by(SupplyChain.relation_type, SupplyChain.importance)
            .limit(30)
        )
        ups: list[str] = []
        downs: list[str] = []
        for rel, cname in sc_res.all():
            if rel == "upstream":
                ups.append(cname)
            elif rel == "downstream":
                downs.append(cname)
        upstream = "、".join(ups[:6]) if ups else "（无）"
        downstream = "、".join(downs[:6]) if downs else "（无）"

        return {
            "name": stock.name or stock.code,
            "code": stock.code,
            "industry": stock.industry or "（未知）",
            "segments": segments,
            "upstream": upstream,
            "downstream": downstream,
        }

    def _parse(self, raw: str) -> list[dict]:
        if not raw:
            return []
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
        except Exception as e:
            logger.error(f"[tags_extractor] JSON 解析失败: {e}\n原始: {raw[:300]}")
            return []

        out: list[dict] = []
        for item in data.get("tags", []) or []:
            name = (item.get("name") or "").strip().lstrip("#").strip()
            if not name or len(name) > 16:
                continue
            category = item.get("category") or "theme"
            if category not in VALID_CATEGORIES:
                category = "theme"
            try:
                conf_raw = item.get("confidence")
                confidence = float(conf_raw) if conf_raw is not None else None
            except (TypeError, ValueError):
                confidence = None
            out.append({
                "name": name,
                "category": category,
                "confidence": confidence,
            })
        # 去重保留最高 confidence
        dedup: dict[str, dict] = {}
        for t in out:
            cur = dedup.get(t["name"])
            if cur is None or (t["confidence"] or 0) > (cur["confidence"] or 0):
                dedup[t["name"]] = t
        return list(dedup.values())
