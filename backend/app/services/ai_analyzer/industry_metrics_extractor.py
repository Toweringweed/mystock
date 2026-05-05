"""从 SEC 10-Q 文本中用 LLM 提取行业景气数据点

NVDA → datacenter_revenue
GOOGL/META/MSFT/AMZN → capex_guidance / capex_actual
"""
import json
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings as app_settings
from app.models.industry_metric import IndustryMetric
from app.services.settings_service import get_effective_value

logger = logging.getLogger(__name__)


@dataclass
class MetricResult:
    metric_name: str
    period: str
    value: float | None
    unit: str | None
    extracted_quote: str | None


PROMPT_TEMPLATES = {
    "NVDA": """从下面的 NVIDIA 10-Q 节选中提取数据中心 (Data Center) 业务相关数据。

文本：
---
{text}
---

输出 JSON（无任何多余文字）：
{{
  "datacenter_revenue": {{ "value": <number>, "unit": "USD_billion", "period": "2026Q1", "quote": "..." }},
  "datacenter_revenue_yoy": {{ "value": <pct as number>, "unit": "pct", "period": "2026Q1", "quote": "..." }},
  "guidance_next_q_revenue": {{ "value": <number>, "unit": "USD_billion", "period": "2026Q2", "quote": "..." }}
}}

字段说明：
- value 用十亿美元计（25.5 表示 $25.5B）
- period 用 YYYYQn 格式
- 如某项数据未在文本中出现，对应字段设为 null
""",

    "CSP": """从下面的 {company} 10-Q 节选中提取资本开支 (Capital Expenditures) 数据。

文本：
---
{text}
---

输出 JSON（无任何多余文字）：
{{
  "capex_actual": {{ "value": <number>, "unit": "USD_billion", "period": "2026Q1", "quote": "..." }},
  "capex_guidance_full_year": {{ "value": <number>, "unit": "USD_billion", "period": "2026", "quote": "..." }}
}}

字段说明：
- 关注 "AI infrastructure" / "data centers" / "servers" 相关的 capex
- 没有明确披露则字段设为 null
""",
}


async def extract(
    db: AsyncSession, ticker: str, text: str, period_hint: str
) -> list[MetricResult]:
    """从 10-Q 文本提取指标。返回结构化结果列表（不写库）"""
    if not text:
        return []

    if ticker.upper() == "NVDA":
        prompt = PROMPT_TEMPLATES["NVDA"].format(text=text[:8000])
    else:
        prompt = PROMPT_TEMPLATES["CSP"].format(company=ticker.upper(), text=text[:8000])

    from app.services.ai_analyzer.llm_client import call_llm
    try:
        raw = await call_llm(db, prompt, max_tokens=1500, prefer_haiku=True)
    except Exception as e:
        logger.error(f"[industry_metrics][{ticker}] LLM 调用失败: {e}")
        return []

    try:
        s = raw.find("{")
        e = raw.rfind("}") + 1
        data = json.loads(raw[s:e]) if s >= 0 and e > s else {}
    except Exception as ex:
        logger.warning(f"[industry_metrics][{ticker}] JSON 解析失败: {ex}")
        return []

    results: list[MetricResult] = []
    name_prefix = ticker.lower()
    for field, item in data.items():
        if not isinstance(item, dict):
            continue
        val = item.get("value")
        if val is None:
            continue
        try:
            results.append(MetricResult(
                metric_name=f"{name_prefix}_{field}",
                period=str(item.get("period") or period_hint),
                value=float(val),
                unit=item.get("unit"),
                extracted_quote=item.get("quote"),
            ))
        except (TypeError, ValueError):
            continue
    return results


async def save_metrics(
    db: AsyncSession,
    metrics: list[MetricResult],
    source: str,
    extracted_from: str,
) -> int:
    saved = 0
    for m in metrics:
        stmt = pg_insert(IndustryMetric).values(
            metric_name=m.metric_name,
            period=m.period,
            value=m.value,
            unit=m.unit,
            source=source,
            extracted_from=extracted_from,
            extracted_quote=m.extracted_quote,
        ).on_conflict_do_update(
            index_elements=["metric_name", "period", "source"],
            set_={
                "value": m.value,
                "unit": m.unit,
                "extracted_from": extracted_from,
                "extracted_quote": m.extracted_quote,
            },
        )
        await db.execute(stmt)
        saved += 1
    return saved
