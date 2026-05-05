"""财报追踪 Celery 任务

包含三个定时任务:
1. backfill_earnings_actuals — 从 stock_fundamentals (quarterly) 自动套填 earnings_surprises 的 actual 字段
2. compute_earnings_returns — 重算已披露财报的前后股价反应(适合刚到 30 日窗口的)
3. detect_upcoming_earnings — 扫描 industry_news 中"预约披露日"等公告,补充 calendar_events
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from celery import shared_task
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.earnings_surprise import EarningsSurprise
from app.models.fundamental import ProfitForecast, StockFundamental
from app.models.kline import StockDailyKline
from app.models.stock import Stock

logger = logging.getLogger(__name__)


def _classify(pct: Decimal | None) -> str | None:
    if pct is None:
        return None
    p = float(pct)
    if p >= 5: return "beat"
    if p <= -5: return "miss"
    return "meet"


async def _compute_returns_for(stock_id: int, release_date: date, db) -> dict:
    """计算财报前后股价反应(简化版 — 复用 endpoint 中的逻辑)"""
    # base = release_date 当日或之后第一个交易日
    res = await db.execute(
        select(StockDailyKline.close, StockDailyKline.trade_date)
        .where(StockDailyKline.stock_id == stock_id)
        .where(StockDailyKline.trade_date >= release_date)
        .order_by(StockDailyKline.trade_date.asc())
        .limit(1)
    )
    base = res.first()
    if not base:
        return {}
    base_price = float(base.close)
    base_dt = base.trade_date
    out = {"price_at_release": Decimal(str(base_price))}

    async def _ret(n_days: int, direction: int) -> Decimal | None:
        target = base_dt + timedelta(days=n_days * direction)
        if direction > 0:
            q = await db.execute(
                select(StockDailyKline.close)
                .where(StockDailyKline.stock_id == stock_id)
                .where(StockDailyKline.trade_date <= target)
                .where(StockDailyKline.trade_date > base_dt)
                .order_by(StockDailyKline.trade_date.desc()).limit(1)
            )
        else:
            q = await db.execute(
                select(StockDailyKline.close)
                .where(StockDailyKline.stock_id == stock_id)
                .where(StockDailyKline.trade_date >= target)
                .where(StockDailyKline.trade_date < base_dt)
                .order_by(StockDailyKline.trade_date.asc()).limit(1)
            )
        r = q.first()
        if not r:
            return None
        return Decimal(str(round((float(r.close) - base_price) / base_price * 100, 2)))

    out["post_release_1d_return"] = await _ret(1, +1)
    out["post_release_5d_return"] = await _ret(7, +1)
    out["post_release_30d_return"] = await _ret(42, +1)
    out["pre_release_5d_return"] = await _ret(7, -1)
    out["pre_release_20d_return"] = await _ret(28, -1)
    return out


def _parse_period(period_raw: str) -> tuple[int, int] | None:
    """解析 '2026-Q1' / '2026Q1' → (年份, 季度数字)."""
    if not period_raw:
        return None
    s = period_raw.replace("-", "").upper()
    if "Q" not in s:
        return None
    try:
        year_str, q_str = s.split("Q")
        return int(year_str), int(q_str)
    except (ValueError, IndexError):
        return None


async def _backfill_earnings():
    """从 stock_fundamentals 季度数据自动填 earnings_surprises 的 actual 字段.
    同时从 profit_forecasts 反推季度 expected(年度预测 / 4)。"""
    async with AsyncSessionLocal() as db:
        # 预先取所有股票的年度预测 → 用于反推季度 expected
        all_forecasts = await db.execute(
            select(ProfitForecast).where(ProfitForecast.forecast_year >= 2024)
        )
        forecasts_by_stock_year: dict[tuple[int, int], ProfitForecast] = {}
        for f in all_forecasts.scalars().all():
            key = (f.stock_id, f.forecast_year)
            # 优先级:manual > llm > ths/wind
            existing = forecasts_by_stock_year.get(key)
            if not existing or (f.source == "manual" and existing.source != "manual"):
                forecasts_by_stock_year[key] = f

        # 取所有 quarterly 数据(最近 180 天 updated_at 内的)
        cutoff = datetime.utcnow() - timedelta(days=180)
        res = await db.execute(
            select(StockFundamental, Stock)
            .join(Stock, Stock.id == StockFundamental.stock_id)
            .where(StockFundamental.period_type == "quarterly")
            .where(StockFundamental.updated_at >= cutoff)
        )
        rows = res.all()
        upserted = 0

        for fund, stock in rows:
            parsed = _parse_period(fund.period or "")
            if not parsed:
                continue  # 跳过非季度数据
            year, quarter = parsed
            period = f"{year}Q{quarter}"

            release_date = fund.updated_at.date() if fund.updated_at else date.today()
            returns = await _compute_returns_for(stock.id, release_date, db)

            # 反推季度 expected:用年度预测 / 4 作为简化假设(若有)
            year_forecast = forecasts_by_stock_year.get((stock.id, year))
            expected_revenue_yi = None
            expected_net_profit_yi = None
            expected_source = None
            if year_forecast:
                if year_forecast.net_profit_forecast:
                    expected_net_profit_yi = Decimal(
                        str(round(float(year_forecast.net_profit_forecast) / 1e8 / 4, 2))
                    )
                expected_source = f"年度预测/4 ({year_forecast.source})"

            values = {
                "stock_id": stock.id,
                "period_type": "quarterly",
                "period": period,
                "release_date": release_date,
                # expected 字段(仅在记录尚不存在时,后端 ON CONFLICT 不会覆盖手填值)
                "expected_revenue_yi": expected_revenue_yi,
                "expected_net_profit_yi": expected_net_profit_yi,
                "expected_source": expected_source,
                # actual 字段
                "actual_revenue_yi": Decimal(str(round(float(fund.revenue) / 1e8, 2))) if fund.revenue else None,
                "actual_net_profit_yi": Decimal(str(round(float(fund.net_profit) / 1e8, 2))) if fund.net_profit else None,
                "actual_eps": Decimal(str(fund.eps)) if fund.eps else None,
                "actual_yoy_growth": Decimal(str(fund.profit_yoy)) if fund.profit_yoy else None,
                "data_source": "auto_track",
                "updated_at": datetime.utcnow(),
                **returns,
            }
            stmt = pg_insert(EarningsSurprise).values(**values)
            # ON CONFLICT 时:只更新 actual_*/post_*/pre_*/price_at_release/updated_at
            # expected_* 字段保留(避免覆盖手填值或更精准的 Skill 写入)
            update_cols = {
                k: stmt.excluded[k]
                for k in values.keys()
                if k.startswith("actual_")
                or k.startswith("post_")
                or k.startswith("pre_")
                or k == "price_at_release"
                or k == "updated_at"
            }
            # 但 expected 字段仅在 NULL 时填充(COALESCE 模式)
            for ek in ("expected_revenue_yi", "expected_net_profit_yi", "expected_source"):
                if ek in values:
                    update_cols[ek] = func.coalesce(EarningsSurprise.__table__.c[ek], stmt.excluded[ek])
            stmt = stmt.on_conflict_do_update(
                constraint="uq_earnings_surprise_stock_period",
                set_=update_cols,
            )
            try:
                await db.execute(stmt)
                upserted += 1
            except Exception as e:
                logger.warning(f"backfill failed for {stock.code} {period}: {e}")
                await db.rollback()
                continue

        await db.commit()
        logger.info(f"earnings_backfill: upserted {upserted} records from {len(rows)} quarterly fundamentals")
        return upserted


async def _recompute_returns():
    """对最近 60 天披露的记录,重算 post_release_30d_return(等待 30 日窗口到位)."""
    async with AsyncSessionLocal() as db:
        cutoff = date.today() - timedelta(days=60)
        res = await db.execute(
            select(EarningsSurprise)
            .where(EarningsSurprise.release_date >= cutoff)
            .where(EarningsSurprise.post_release_30d_return.is_(None))
        )
        records = res.scalars().all()
        updated = 0
        for r in records:
            returns = await _compute_returns_for(r.stock_id, r.release_date, db)
            if not returns:
                continue
            for k, v in returns.items():
                if v is not None and getattr(r, k) is None:
                    setattr(r, k, v)
            updated += 1
        await db.commit()
        logger.info(f"earnings_returns_recompute: updated {updated} records")
        return updated


# ────────────────── Celery shared tasks ──────────────────

@shared_task(name="app.tasks.earnings_tasks.backfill_earnings_actuals")
def backfill_earnings_actuals():
    """每日:从 stock_fundamentals 季度数据自动套填 earnings_surprises actual."""
    return asyncio.run(_backfill_earnings())


@shared_task(name="app.tasks.earnings_tasks.compute_earnings_returns")
def compute_earnings_returns():
    """每日:补算最近 60 日披露记录的 post_release_*_return."""
    return asyncio.run(_recompute_returns())


# ────────────────── 财报日历扫描 ──────────────────

import re

# 公告标题中的财报披露日期识别模式
EARNINGS_ANNOUNCE_PATTERNS = [
    r"业绩预约披露日",
    r"年报披露时间",
    r"季报披露时间",
    r"关于(?:举行|召开).*?(?:业绩说明会|年度业绩|季度业绩|一季度|半年度|三季度|年度)",
    r"\d{4}\s*年\s*(?:第[一二三四]季度|半年度|年度)\s*报告",
]

DATE_PATTERN = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def _extract_release_date(text: str) -> date | None:
    """从公告标题/摘要里提取披露日期(简化版,先做日期匹配,不做语义提取)."""
    if not text:
        return None
    m = DATE_PATTERN.search(text)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except (ValueError, TypeError):
        return None


async def _scan_announcements_for_earnings():
    """扫描 industry_news 中含财报披露关键词的公告,自动写入 calendar_events.
    简化策略:仅识别"业绩预约披露"+ 标题含未来日期。"""
    from app.models.calendar_event import CalendarEvent
    from app.models.news import IndustryNews, NewsStockRelation

    async with AsyncSessionLocal() as db:
        # 取最近 30 天的公告
        cutoff = datetime.utcnow() - timedelta(days=30)
        announces_q = await db.execute(
            select(IndustryNews, NewsStockRelation)
            .join(NewsStockRelation, NewsStockRelation.news_id == IndustryNews.id)
            .where(IndustryNews.published_at >= cutoff)
            .where(IndustryNews.category == "announcement")
        )
        rows = announces_q.all()

        added = 0
        for news, rel in rows:
            title = news.title or ""
            # 必须命中财报关键词
            if not any(re.search(p, title) for p in EARNINGS_ANNOUNCE_PATTERNS):
                continue

            # 尝试从标题提取日期(若公告含"预约披露日 2026-04-30")
            extracted_date = _extract_release_date(title) or _extract_release_date(news.summary or "")
            if not extracted_date:
                continue
            # 仅处理未来日期(已披露的不需要日历事件)
            if extracted_date < date.today():
                continue

            # upsert calendar_event(stock_id + event_type + event_date 唯一)
            try:
                await db.execute(
                    pg_insert(CalendarEvent).values(
                        stock_id=rel.stock_id,
                        event_type="earnings_release",
                        event_date=extracted_date,
                        title=title[:200],
                        payload={"source_news_id": news.id, "extracted_from": "announcement_scan"},
                    ).on_conflict_do_nothing()
                )
                added += 1
            except Exception as e:
                logger.warning(f"calendar add failed: {e}")
                await db.rollback()

        await db.commit()
        logger.info(f"calendar_scan: added {added} earnings dates from {len(rows)} announcements")
        return added


@shared_task(name="app.tasks.earnings_tasks.scan_earnings_calendar")
def scan_earnings_calendar():
    """每日:扫描 industry_news 公告,自动提取财报披露日期到 calendar_events."""
    return asyncio.run(_scan_announcements_for_earnings())
