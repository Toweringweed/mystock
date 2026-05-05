"""净利润预测生成器(机构一致预期 + LLM 兜底)

数据源优先级:
  1. manual    : 用户手工录入,从不被覆盖
  2. ths       : 同花顺 i问财机构一致预期(免费,带分析师覆盖数 + 最小/均值/最大区间)
  3. llm       : LLM 估算(仅当 ths 无数据时降级使用)

write 时:
  - 同年份对应同 source 时 ON CONFLICT DO UPDATE
  - 如有同年份 manual 记录则跳过任何写入
"""
import json
import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.fundamental import ProfitForecast, StockFundamental
from app.models.kline import StockDailyKline
from app.models.stock import Stock

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 入口:先 ths 后 llm 兜底
# ──────────────────────────────────────────────────────────────────────

async def update_profit_forecasts(db: AsyncSession, code: str) -> dict:
    """更新某只股票的盈利预测(优先同花顺真实机构数据,降级 LLM)

    返回 {"source": "ths|llm|skipped", "rows": N, "years": [...]}
    """
    stock_row = await db.execute(select(Stock).where(Stock.code == code))
    stock = stock_row.scalar_one_or_none()
    if not stock:
        raise ValueError(f"股票 {code} 不存在")

    # 1. 先尝试同花顺真实数据
    n_ths, years_ths = await _save_ths_forecasts(db, stock)
    if n_ths > 0:
        await db.flush()
        logger.info(f"[{code}] 同花顺一致预期写入 {n_ths} 行,覆盖 {years_ths}")
        return {"source": "ths", "rows": n_ths, "years": years_ths}

    # 2. 降级 LLM(仅小盘股 / 新股 / 同花顺无覆盖时)
    logger.info(f"[{code}] 同花顺无覆盖,降级 LLM 兜底")
    n_llm, years_llm = await _save_llm_forecasts(db, stock)
    await db.flush()
    return {"source": "llm" if n_llm else "skipped", "rows": n_llm, "years": years_llm}


# 兼容旧 API 命名(api/v1/endpoints/analysis.py:llm_forecast 调用此函数)
async def generate_llm_forecast(db: AsyncSession, code: str) -> dict:
    """旧入口名,已改为先真实数据后 LLM 兜底"""
    return await update_profit_forecasts(db, code)


# ──────────────────────────────────────────────────────────────────────
# 同花顺真实数据
# ──────────────────────────────────────────────────────────────────────

async def _save_ths_forecasts(db: AsyncSession, stock: Stock) -> tuple[int, list[int]]:
    from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
    fetcher = AKShareFetcher()
    try:
        rows = await fetcher.fetch_profit_forecasts(stock.code)
    except Exception as e:
        logger.warning(f"[{stock.code}] 同花顺接口失败: {e}")
        return 0, []
    if not rows:
        return 0, []

    # 取最新收盘价用于算 forward_pe
    latest_close = await _latest_close(db, stock.id)
    market_cap = await _market_cap_estimate(db, stock.id)

    saved_years: list[int] = []
    for r in rows:
        year = r["forecast_year"]
        if await _has_manual(db, stock.id, year):
            continue

        eps_avg = r.get("eps_avg")
        np_avg = r.get("net_profit_avg")  # 已转 元

        # forward_pe 优先用 EPS avg(price / eps),兜底用市值/净利
        forward_pe = None
        if eps_avg and latest_close:
            forward_pe = float(latest_close) / eps_avg
        elif np_avg and market_cap:
            forward_pe = market_cap / np_avg

        values = {
            "stock_id": stock.id,
            "forecast_year": year,
            "eps_forecast": eps_avg,
            "net_profit_forecast": np_avg,
            "forward_pe": forward_pe,
            "analyst_count": r.get("analyst_count"),
            "source": "ths",
        }
        stmt = insert(ProfitForecast).values(**values).on_conflict_do_update(
            constraint="uq_forecast_stock_year_source",
            set_={
                "eps_forecast": values["eps_forecast"],
                "net_profit_forecast": values["net_profit_forecast"],
                "forward_pe": values["forward_pe"],
                "analyst_count": values["analyst_count"],
            },
        )
        await db.execute(stmt)
        saved_years.append(year)
    return len(saved_years), saved_years


async def _latest_close(db: AsyncSession, stock_id: int) -> float | None:
    row = await db.execute(
        select(StockDailyKline.close)
        .where(StockDailyKline.stock_id == stock_id)
        .order_by(StockDailyKline.trade_date.desc()).limit(1)
    )
    v = row.scalar_one_or_none()
    return float(v) if v is not None else None


async def _market_cap_estimate(db: AsyncSession, stock_id: int) -> float | None:
    """从最新 TTM PE × 净利润反推市值"""
    row = await db.execute(
        select(StockFundamental.pe_ttm, StockFundamental.net_profit)
        .where(StockFundamental.stock_id == stock_id, StockFundamental.period_type == "ttm")
        .order_by(StockFundamental.updated_at.desc()).limit(1)
    )
    rec = row.one_or_none()
    if not rec:
        return None
    pe, np_v = rec
    if pe and np_v and float(np_v) > 0:
        return float(pe) * float(np_v)
    return None


async def _has_manual(db: AsyncSession, stock_id: int, year: int) -> bool:
    row = await db.execute(
        select(ProfitForecast.id).where(
            ProfitForecast.stock_id == stock_id,
            ProfitForecast.forecast_year == year,
            ProfitForecast.source == "manual",
        )
    )
    return row.scalar_one_or_none() is not None


# ──────────────────────────────────────────────────────────────────────
# LLM 兜底(同花顺无覆盖时)
# ──────────────────────────────────────────────────────────────────────

LLM_PROMPT = """你是一位资深A股研究员。请根据以下信息,估算 {name}({code}) 2026 年和 2027 年的机构研报平均净利润预测。

【公司基本信息】
- 行业: {industry}
- 当前 PE-TTM: {pe_ttm}
- 近12个月净利润(TTM): {net_profit_ttm} 亿元
- 毛利率: {gross_margin}%
- 净利润同比增速: {profit_yoy}%

输出 JSON(只输出 JSON):
{{
  "forecast_2026": 100.5,
  "forecast_2027": 130.0,
  "reasoning": "1-2 句话依据"
}}
单位:亿元人民币。"""


async def _save_llm_forecasts(db: AsyncSession, stock: Stock) -> tuple[int, list[int]]:
    fund_row = await db.execute(
        select(StockFundamental)
        .where(StockFundamental.stock_id == stock.id, StockFundamental.period_type == "ttm")
        .order_by(StockFundamental.updated_at.desc()).limit(1)
    )
    fund = fund_row.scalar_one_or_none()

    def _v(col: str) -> str:
        if fund is None: return "N/A"
        v = getattr(fund, col, None)
        return str(round(float(v), 2)) if v is not None else "N/A"

    np_ttm = (
        str(round(float(fund.net_profit) / 1e8, 2))
        if fund and fund.net_profit is not None else "N/A"
    )
    prompt = LLM_PROMPT.format(
        name=stock.name, code=stock.code,
        industry=stock.industry or "未知",
        pe_ttm=_v("pe_ttm"), net_profit_ttm=np_ttm,
        gross_margin=_v("gross_margin"), profit_yoy=_v("profit_yoy"),
    )

    raw = await _call_llm(prompt, db=db)
    data = _parse(raw)
    f26 = data.get("forecast_2026")
    f27 = data.get("forecast_2027")
    if f26 is None and f27 is None:
        return 0, []

    latest_close = await _latest_close(db, stock.id)

    saved_years: list[int] = []
    for year, np_yi in [(2026, f26), (2027, f27)]:
        if np_yi is None or await _has_manual(db, stock.id, year):
            continue
        np_yuan = float(np_yi) * 1e8
        forward_pe = None
        # LLM 不出 EPS,只能用市值/净利估
        market_cap = await _market_cap_estimate(db, stock.id)
        if market_cap and np_yuan > 0:
            forward_pe = market_cap / np_yuan

        stmt = insert(ProfitForecast).values(
            stock_id=stock.id, forecast_year=year,
            net_profit_forecast=np_yuan,
            forward_pe=forward_pe,
            source="llm",
        ).on_conflict_do_update(
            constraint="uq_forecast_stock_year_source",
            set_={
                "net_profit_forecast": np_yuan,
                "forward_pe": forward_pe,
            },
        )
        await db.execute(stmt)
        saved_years.append(year)
    return len(saved_years), saved_years


async def _call_llm(prompt: str, db=None) -> str:
    async def _get(key: str) -> str:
        if db is not None:
            try:
                from app.services.settings_service import get_effective_value
                return await get_effective_value(db, key)
            except Exception:
                pass
        return str(getattr(settings, key, "") or "")

    try:
        or_key = await _get("openrouter_api_key")
        or_model = await _get("openrouter_model") or settings.openrouter_model
        if or_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")
            resp = await client.chat.completions.create(
                model=or_model, messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=500,
            )
            return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"OpenRouter 预测失败: {e}")

    try:
        oai_key = await _get("openai_api_key")
        oai_model = await _get("openai_model") or settings.openai_model
        if oai_key:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=oai_key)
            resp = await client.chat.completions.create(
                model=oai_model, messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=500,
            )
            return resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"OpenAI 预测失败: {e}")

    try:
        ant_key = await _get("anthropic_api_key")
        ant_model = await _get("anthropic_model") or settings.anthropic_model
        if ant_key:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=ant_key)
            resp = await client.messages.create(
                model=ant_model, max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
    except Exception as e:
        logger.error(f"Anthropic 预测失败: {e}")
    return ""


def _parse(raw: str) -> dict:
    if not raw:
        return {}
    try:
        s = raw.find("{"); e = raw.rfind("}") + 1
        if s >= 0 and e > s:
            return json.loads(raw[s:e])
    except Exception:
        pass
    return {}
