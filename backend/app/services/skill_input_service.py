"""stock-analysis skill 一次性数据聚合 — 替代多次 SQL 查询。

返回大 JSON, skill 用 curl GET /api/v1/analysis/{code}/skill-input 一次拿全。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _to_jsonable(v):
    """把 Decimal / datetime / date 转成 JSON 友好类型"""
    from decimal import Decimal
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _row_to_dict(row, exclude: tuple = ()) -> dict:
    """SQLAlchemy ORM 实例 → dict,自动转 JSON 友好类型"""
    out = {}
    for col in row.__table__.columns:
        if col.name in exclude:
            continue
        out[col.name] = _to_jsonable(getattr(row, col.name))
    return out


async def build_skill_input(db: AsyncSession, code: str) -> dict | None:
    from app.models.analysis import AnalysisReport, DivergenceSignal
    from app.models.business_segment import BusinessSegment
    from app.models.calendar_event import CalendarEvent
    from app.models.event import StockEvent
    from app.models.fundamental import ProfitForecast, StockFundamental
    from app.models.industry_metric import IndustryMetric
    from app.models.insider_trade import InsiderTrade
    from app.models.kline import StockDailyKline, StockTechnicalIndicator
    from app.models.news import IndustryNews, NewsStockRelation
    from app.models.research import ResearchReportMeta
    from app.models.stock import Stock
    from app.models.target_price_realtime import StockTargetPriceRealtime

    # ── 1. 基本信息 ─────────────────────────────────────
    s_q = await db.execute(select(Stock).where(Stock.code == code))
    stock: Stock | None = s_q.scalar_one_or_none()
    if not stock:
        return None

    basic = {
        "code": stock.code,
        "name": stock.name,
        "market": stock.market,
        "industry": stock.industry,
        "sector": stock.sector,
        "is_watchlist": stock.is_watchlist,
        "is_core": stock.is_core,
        "data_ready": stock.data_ready,
    }

    # ── 2. K 线 + 技术指标(近 60 日) ────────────────────
    kline_q = await db.execute(
        select(StockDailyKline)
        .where(StockDailyKline.stock_id == stock.id)
        .order_by(desc(StockDailyKline.trade_date))
        .limit(60)
    )
    klines = list(kline_q.scalars().all())

    ind_q = await db.execute(
        select(StockTechnicalIndicator)
        .where(StockTechnicalIndicator.stock_id == stock.id)
        .order_by(desc(StockTechnicalIndicator.trade_date))
        .limit(60)
    )
    inds = {i.trade_date: i for i in ind_q.scalars().all()}

    kline_rows = []
    for k in klines:
        ind = inds.get(k.trade_date)
        kline_rows.append({
            "trade_date": k.trade_date.isoformat(),
            "open": _to_jsonable(k.open),
            "high": _to_jsonable(k.high),
            "low": _to_jsonable(k.low),
            "close": _to_jsonable(k.close),
            "volume": k.volume,
            "change_pct": _to_jsonable(k.change_pct),
            "turnover": _to_jsonable(getattr(k, "turnover", None)),
            "volume_ratio": _to_jsonable(getattr(k, "volume_ratio", None)),
            "ma5": _to_jsonable(getattr(ind, "ma5", None) if ind else None),
            "ma20": _to_jsonable(getattr(ind, "ma20", None) if ind else None),
            "ma60": _to_jsonable(getattr(ind, "ma60", None) if ind else None),
            "macd_hist": _to_jsonable(getattr(ind, "macd_hist", None) if ind else None),
            "rsi_14": _to_jsonable(getattr(ind, "rsi_14", None) if ind else None),
        })

    # 现价 + 5d/20d/60d 涨跌
    current_price = float(klines[0].close) if klines and klines[0].close is not None else None
    def pct_back(n: int) -> float | None:
        if len(klines) <= n or klines[n].close is None or klines[0].close is None:
            return None
        return round((float(klines[0].close) / float(klines[n].close) - 1) * 100, 2)
    basic["current_price"] = current_price
    basic["pct_5d"] = pct_back(5)
    basic["pct_20d"] = pct_back(20)
    basic["pct_60d"] = pct_back(60)

    # ── 3. 背离 ───────────────────────────────────────
    div_q = await db.execute(
        select(DivergenceSignal)
        .where(DivergenceSignal.stock_id == stock.id)
        .order_by(desc(DivergenceSignal.detected_date))
        .limit(10)
    )
    divergences = [_row_to_dict(d) for d in div_q.scalars().all()]

    # ── 4. 财务 TTM + 近 6 季度 ────────────────────────
    ttm_q = await db.execute(
        select(StockFundamental)
        .where(StockFundamental.stock_id == stock.id, StockFundamental.period_type == "ttm")
        .order_by(desc(StockFundamental.updated_at))
        .limit(1)
    )
    ttm_row = ttm_q.scalar_one_or_none()
    ttm = _row_to_dict(ttm_row) if ttm_row else None

    q_q = await db.execute(
        select(StockFundamental)
        .where(StockFundamental.stock_id == stock.id, StockFundamental.period_type == "quarterly")
        .order_by(desc(StockFundamental.period))
        .limit(6)
    )
    quarterlies = [_row_to_dict(r) for r in q_q.scalars().all()]

    # ── 5. 一致预期(2026/2027) ────────────────────────
    pf_q = await db.execute(
        select(ProfitForecast)
        .where(ProfitForecast.stock_id == stock.id, ProfitForecast.forecast_year.in_([2026, 2027]))
        .order_by(ProfitForecast.forecast_year, desc(ProfitForecast.updated_at))
    )
    forecasts = [_row_to_dict(r) for r in pf_q.scalars().all()]

    # ── 6. v5 实时目标价 ─────────────────────────────
    tp_q = await db.execute(
        select(StockTargetPriceRealtime)
        .where(StockTargetPriceRealtime.stock_id == stock.id)
        .order_by(desc(StockTargetPriceRealtime.updated_at))
        .limit(1)
    )
    tp_row = tp_q.scalar_one_or_none()
    target_price = _row_to_dict(tp_row) if tp_row else None

    # ── 7. 资讯 / 公告(近 7 日,按 importance) ─────────
    news_q = await db.execute(
        select(IndustryNews)
        .join(NewsStockRelation, NewsStockRelation.news_id == IndustryNews.id)
        .where(
            NewsStockRelation.stock_id == stock.id,
            IndustryNews.published_at >= datetime.now() - timedelta(days=7),
        )
        .order_by(desc(IndustryNews.importance_score), desc(IndustryNews.published_at))
        .limit(30)
    )
    news_rows = []
    for n in news_q.scalars().all():
        news_rows.append({
            "id": n.id,
            "title": n.title,
            "summary": n.summary,
            "source": n.source,
            "category": n.category,
            "urgency": n.urgency,
            "direction": n.direction,
            "sentiment": n.sentiment,
            "importance_score": _to_jsonable(n.importance_score),
            "catalyst_type": n.catalyst_type,
            "catalyst_summary": n.catalyst_summary,
            "key_risks": n.key_risks,
            "published_at": _to_jsonable(n.published_at),
            "source_url": n.source_url,
        })

    # ── 8. 研报 meta(近 30 日) ──────────────────────
    rr_q = await db.execute(
        select(ResearchReportMeta, IndustryNews)
        .join(IndustryNews, ResearchReportMeta.news_id == IndustryNews.id)
        .where(
            ResearchReportMeta.stock_id == stock.id,
            IndustryNews.published_at >= datetime.now() - timedelta(days=30),
        )
        .order_by(desc(IndustryNews.published_at))
        .limit(20)
    )
    research_rows = []
    for rmeta, news in rr_q.all():
        research_rows.append({
            "title": news.title,
            "broker": rmeta.broker,
            "rating": rmeta.rating,
            "forecast_year_base": rmeta.forecast_year_base,
            "eps_y1": _to_jsonable(rmeta.eps_y1),
            "eps_y2": _to_jsonable(rmeta.eps_y2),
            "eps_y3": _to_jsonable(rmeta.eps_y3),
            "pe_y1": _to_jsonable(rmeta.pe_y1),
            "pe_y2": _to_jsonable(rmeta.pe_y2),
            "pe_y3": _to_jsonable(rmeta.pe_y3),
            "summary": news.summary,
            "published_at": _to_jsonable(news.published_at),
            "pdf_url": rmeta.pdf_url,
        })

    # ── 9. 事件流水(近 30 日) ────────────────────────
    ev_q = await db.execute(
        select(StockEvent)
        .where(
            StockEvent.stock_id == stock.id,
            StockEvent.triggered_at >= datetime.now() - timedelta(days=30),
        )
        .order_by(desc(StockEvent.triggered_at))
        .limit(30)
    )
    events = [_row_to_dict(e) for e in ev_q.scalars().all()]

    # ── 10. 减持/增持(近 180 日) ────────────────────
    it_q = await db.execute(
        select(InsiderTrade)
        .where(
            InsiderTrade.stock_id == stock.id,
            InsiderTrade.ann_date >= date.today() - timedelta(days=180),
        )
        .order_by(desc(InsiderTrade.ann_date))
        .limit(20)
    )
    insiders = [_row_to_dict(r) for r in it_q.scalars().all()]

    # ── 11. 财报/解禁日历(未来 90 日) ────────────────
    cal_q = await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.stock_id == stock.id,
            CalendarEvent.event_date >= date.today(),
            CalendarEvent.event_date <= date.today() + timedelta(days=90),
        )
        .order_by(CalendarEvent.event_date)
    )
    calendar = [_row_to_dict(r) for r in cal_q.scalars().all()]

    # ── 12. 业务分部 ──────────────────────────────────
    seg_q = await db.execute(
        select(BusinessSegment)
        .where(BusinessSegment.stock_id == stock.id)
        .order_by(desc(BusinessSegment.report_period), desc(BusinessSegment.revenue))
    )
    segments = [_row_to_dict(r) for r in seg_q.scalars().all()]

    # ── 13. 行业景气(NVDA + 4 大 CSP 最新季度) ────────
    im_q = await db.execute(
        select(IndustryMetric)
        .where(IndustryMetric.metric_name.like("%datacenter%") | IndustryMetric.metric_name.like("%capex%"))
        .order_by(desc(IndustryMetric.period))
        .limit(30)
    )
    industry_metrics = [_row_to_dict(r) for r in im_q.scalars().all()]

    # ── 14. 历史 AI 报告(近 5 份) ────────────────────
    rep_q = await db.execute(
        select(AnalysisReport)
        .where(AnalysisReport.stock_id == stock.id)
        .order_by(desc(AnalysisReport.generated_at))
        .limit(5)
    )
    prior_reports = []
    for r in rep_q.scalars().all():
        prior_reports.append({
            "report_date": _to_jsonable(r.report_date),
            "report_type": r.report_type,
            "overall_signal": r.overall_signal,
            "conclusion": r.conclusion,
            "technical_score": r.technical_score,
            "fundamental_score": r.fundamental_score,
            "generated_at": _to_jsonable(r.generated_at),
            "full_report": r.full_report,
        })

    # ── 15. 同行业可比标的(从自选股,2-3 个) ───────────
    peers = []
    if stock.industry:
        peer_q = await db.execute(
            select(Stock.code, Stock.name)
            .where(
                Stock.industry == stock.industry,
                Stock.is_watchlist == True,  # noqa: E712
                Stock.id != stock.id,
            )
            .limit(3)
        )
        peers = [{"code": c, "name": n} for c, n in peer_q.all()]

    return {
        "basic": basic,
        "kline_60d": kline_rows,
        "divergence_signals": divergences,
        "fundamentals_ttm": ttm,
        "fundamentals_quarterly": quarterlies,
        "profit_forecasts": forecasts,
        "target_price_v5": target_price,
        "news_7d": news_rows,
        "research_30d": research_rows,
        "events_30d": events,
        "insider_trades_180d": insiders,
        "calendar_90d": calendar,
        "business_segments": segments,
        "industry_metrics": industry_metrics,
        "prior_reports": prior_reports,
        "peers_in_watchlist": peers,
    }
