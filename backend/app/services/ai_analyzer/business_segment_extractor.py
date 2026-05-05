"""业务分部 LLM 提取器(支持 SOTP 拆解估值)

输入:股票 code + 名称 + 年报"分部信息"章节文本
输出:list[Segment] 结构化数据,写入 business_segments 表

category 枚举与含义(给 LLM 用):
  - core   : 公司主业,营收占比最大的传统业务(用周期股/价值股 PE 锚)
  - legacy : 已并表海外/历史业务(独立估值锚,如欧洲工业股)
  - growth : 已落地的成长性新业务(可享受成长溢价)
  - option : 期权/未量产/概念性业务(纯故事溢价,不进现金流模型)

参考用例(潍柴动力 2025H1):
  core   : 重卡发动机+整车         55%  → PE 锚 10-12
  legacy : KION 物流设备           39%  → PE 锚 12-15
  growth : 数据中心柴发(M 系列)    3%   → PE 锚 20-25
  option : SOFC 燃料电池           <0.1% → 纯期权,不计 PE
"""
import json
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


EXTRACT_PROMPT = """你是一位专业的A股研究员,需要从年报中识别 {name}(代码 {code})的业务分部结构,
为投资者做 SOTP(分部估值)分析。

请根据以下年报"分部信息/营业收入构成/经营情况分析"章节文本,识别每个独立业务板块。

文本:
---
{text}
---

请严格按以下 JSON 格式输出(不要有任何多余文字):
{{
  "report_period": "2025A",
  "segments": [
    {{
      "segment_name": "重卡发动机及整车",
      "category": "core",
      "revenue_yi": 1234.5,
      "revenue_pct": 55.0,
      "profit_yi": 67.8,
      "profit_pct": 50.0,
      "gross_margin": 18.5,
      "growth_yoy": 8.5,
      "description": "包括发动机、变速箱、整车,主要面向国内重卡市场"
    }}
  ]
}}

字段说明:
- segment_name: 分部名称,使用公司在年报中的原始措辞,不要发挥
- category 选择(关键!):
  * core   = 公司主业(占营收比 > 30%),用周期/价值股 PE 锚
  * legacy = 已并表海外/历史业务(独立估值,如欧洲工业股)
  * growth = 已落地的成长新业务(已有真实营收 + 高增速 > 50%)
  * option = 期权/未量产/示范项目(营收 < 1% 或纯研发阶段)
- revenue_yi: 营收(亿元),如年报披露单位是元/万元请换算到亿
- revenue_pct: 营收占比 %(0~100),不是 0~1
- profit_yi / profit_pct: 利润数据(若年报未披露分部利润可填 null)
- gross_margin: 该分部的毛利率 %(0~100)
- growth_yoy: 营收同比增速 %(0~+∞)
- description: 1-2 句业务描述,引用年报关键词

要求:
- segment 数量通常 3-7 个,不要过细拆分(如不要把"国内重卡"和"出口重卡"拆开)
- 如果年报只披露按地区拆分(国内/海外),则按地区分类,但 category 全设 core 或 legacy
- 数据为 null 时填 null,不要瞎编
- report_period 从年报标题识别,如"2025年年度报告" → "2025A"
"""


class BusinessSegmentExtractor:
    async def extract(
        self, code: str, name: str, text: str = "", db=None
    ) -> tuple[str | None, list[dict]]:
        """调用 LLM 提取分部数据。返回 (report_period, segments)"""
        if not text:
            logger.warning(f"[{code}] 分部文本为空,无法提取")
            return None, []
        raw = await self._call_llm(code, name, text, db=db)
        return self._parse(raw)

    async def _call_llm(self, code: str, name: str, text: str, db=None) -> str:
        prompt = EXTRACT_PROMPT.format(code=code, name=name, text=text[:8000])

        async def _get(key: str) -> str:
            if db is not None:
                try:
                    from app.services.settings_service import get_effective_value
                    return await get_effective_value(db, key)
                except Exception:
                    pass
            return str(getattr(settings, key, "") or "")

        # ── OpenRouter ────────────────────────────────────────────────
        try:
            or_key = await _get("openrouter_api_key")
            or_model = await _get("openrouter_model") or settings.openrouter_model
            if or_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
                resp = await client.chat.completions.create(
                    model=or_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=2500,
                )
                return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"[{code}] OpenRouter 分部提取失败,尝试下一个: {e}")

        # ── OpenAI ────────────────────────────────────────────────────
        try:
            oai_key = await _get("openai_api_key")
            oai_model = await _get("openai_model") or settings.openai_model
            if oai_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=oai_key)
                resp = await client.chat.completions.create(
                    model=oai_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=2500,
                )
                return resp.choices[0].message.content or ""
        except Exception as e:
            logger.warning(f"[{code}] OpenAI 分部提取失败,尝试下一个: {e}")

        # ── Anthropic ─────────────────────────────────────────────────
        try:
            ant_key = await _get("anthropic_api_key")
            ant_model = await _get("anthropic_model") or settings.anthropic_model
            if ant_key:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=ant_key)
                resp = await client.messages.create(
                    model=ant_model,
                    max_tokens=2500,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text
        except Exception as e:
            logger.error(f"[{code}] Anthropic 分部提取失败: {e}")

        logger.error(f"[{code}] 所有 LLM provider 均失败")
        return ""

    def _parse(self, raw: str) -> tuple[str | None, list[dict]]:
        if not raw:
            return None, []
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            data = json.loads(raw[start:end])
        except Exception as e:
            logger.error(f"分部 JSON 解析失败: {e}\n原始: {raw[:200]}")
            return None, []

        period = (data.get("report_period") or "").strip() or None
        out: list[dict] = []
        for item in data.get("segments", []):
            name = (item.get("segment_name") or "").strip()
            if not name:
                continue
            try:
                rev_yi = item.get("revenue_yi")
                profit_yi = item.get("profit_yi")
                out.append({
                    "segment_name": name,
                    "category": _normalize_category(item.get("category")),
                    "revenue": float(rev_yi) * 1e8 if rev_yi is not None else None,
                    "revenue_pct": _to_float(item.get("revenue_pct")),
                    "profit": float(profit_yi) * 1e8 if profit_yi is not None else None,
                    "profit_pct": _to_float(item.get("profit_pct")),
                    "gross_margin": _to_float(item.get("gross_margin")),
                    "growth_yoy": _to_float(item.get("growth_yoy")),
                    "description": (item.get("description") or "").strip() or None,
                })
            except Exception as e:
                logger.debug(f"分部单条解析失败: {e}")
        return period, out


_VALID_CATEGORIES = {"core", "legacy", "growth", "option"}


def _normalize_category(v) -> str | None:
    if not v:
        return None
    s = str(v).strip().lower()
    return s if s in _VALID_CATEGORIES else None


def _to_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
