"""首页自选股表格数据聚合服务"""
import logging
from datetime import date

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisReport
from app.models.calendar_event import CalendarEvent
from app.models.earnings_surprise import EarningsSurprise
from app.models.fundamental import ProfitForecast, StockFundamental
from app.models.stock import Stock
from app.models.stock_meta import StockNote
from app.models.target_price_realtime import StockTargetPriceRealtime
from app.schemas.analysis import WatchlistTableRow

logger = logging.getLogger(__name__)


async def get_watchlist_table(db: AsyncSession) -> list[WatchlistTableRow]:
    """聚合自选股表格所需的全部数据，每股一行"""
    # 1. 获取自选股列表
    result = await db.execute(
        select(Stock).where(Stock.is_watchlist == True).order_by(Stock.id)
    )
    stocks = list(result.scalars().all())
    if not stocks:
        return []

    stock_ids = [s.id for s in stocks]
    code_to_stock = {s.code: s for s in stocks}
    id_to_stock = {s.id: s for s in stocks}

    # 2. 批量查询最新基本面（TTM）
    fund_result = await db.execute(
        select(StockFundamental)
        .where(
            StockFundamental.stock_id.in_(stock_ids),
            StockFundamental.period_type == "ttm",
        )
        .order_by(StockFundamental.stock_id, StockFundamental.updated_at.desc())
    )
    # 每只股票取最新一条
    fundamentals: dict[int, StockFundamental] = {}
    for f in fund_result.scalars().all():
        if f.stock_id not in fundamentals:
            fundamentals[f.stock_id] = f

    # 3. 批量查询盈利预测（2026/2027），优先 manual > llm > 其他来源
    source_priority = case(
        (ProfitForecast.source == "manual", 0),
        (ProfitForecast.source == "llm", 1),
        else_=2,
    )
    forecast_result = await db.execute(
        select(ProfitForecast)
        .where(
            ProfitForecast.stock_id.in_(stock_ids),
            ProfitForecast.forecast_year.in_([2026, 2027]),
        )
        .order_by(ProfitForecast.stock_id, ProfitForecast.forecast_year, source_priority)
    )
    # {stock_id: {year: ProfitForecast}} — 每个 (stock_id, year) 只取优先级最高的
    forecasts: dict[int, dict[int, ProfitForecast]] = {}
    seen: set[tuple[int, int]] = set()
    for f in forecast_result.scalars().all():
        key = (f.stock_id, f.forecast_year)
        if key not in seen:
            seen.add(key)
            forecasts.setdefault(f.stock_id, {})[f.forecast_year] = f

    # 4. 批量查询最新 AI 报告（取 technical_analysis 字段）
    # 子查询：每个 stock_id 取最新 report_date
    report_result = await db.execute(
        select(AnalysisReport)
        .where(AnalysisReport.stock_id.in_(stock_ids))
        .order_by(AnalysisReport.stock_id, AnalysisReport.generated_at.desc())
    )
    latest_reports: dict[int, AnalysisReport] = {}
    for r in report_result.scalars().all():
        if r.stock_id not in latest_reports:
            latest_reports[r.stock_id] = r

    # 5. 批量查询用户备注（推荐操作）
    note_result = await db.execute(
        select(StockNote).where(StockNote.stock_id.in_(stock_ids))
    )
    notes: dict[int, StockNote] = {n.stock_id: n for n in note_result.scalars().all()}

    # 5.5 批量查询标签
    from app.schemas.tags import TagRead
    from app.services.tags_service import get_tags_for_stocks
    tags_by_stock = await get_tags_for_stocks(db, stock_ids)

    # 5.6 批量查询即将到来的财报披露日(未来 60 天内最近一次)
    today = date.today()
    cal_result = await db.execute(
        select(CalendarEvent.stock_id, CalendarEvent.event_date)
        .where(CalendarEvent.stock_id.in_(stock_ids))
        .where(CalendarEvent.event_type == "earnings_release")
        .where(CalendarEvent.event_date >= today)
        .order_by(CalendarEvent.stock_id, CalendarEvent.event_date.asc())
    )
    upcoming_earnings_map: dict[int, date] = {}
    for row in cal_result.all():
        if row.stock_id not in upcoming_earnings_map:
            upcoming_earnings_map[row.stock_id] = row.event_date

    # 5.7 批量查询每股最新财报 surprise(用于显示上次方向)
    surprise_result = await db.execute(
        select(EarningsSurprise)
        .where(EarningsSurprise.stock_id.in_(stock_ids))
        .order_by(EarningsSurprise.stock_id, EarningsSurprise.release_date.desc())
    )
    last_surprise_map: dict[int, EarningsSurprise] = {}
    for s in surprise_result.scalars().all():
        if s.stock_id not in last_surprise_map:
            last_surprise_map[s.stock_id] = s

    # 5.8 批量查询 v5 实时目标价信号(主决策因子)
    v5_result = await db.execute(
        select(StockTargetPriceRealtime).where(
            StockTargetPriceRealtime.stock_id.in_(stock_ids)
        )
    )
    v5_map: dict[int, StockTargetPriceRealtime] = {
        r.stock_id: r for r in v5_result.scalars().all()
    }

    # 6. 尝试从 Redis 获取实时行情（current_price, ytd_change）
    quotes: dict[str, dict] = {}
    try:
        from app.services.quote_cache import get_quotes
        codes = [s.code for s in stocks]
        quotes = await get_quotes(codes)
    except Exception:
        pass

    # 7. 组装行数据
    rows: list[WatchlistTableRow] = []
    for stock in stocks:
        sid = stock.id
        fund = fundamentals.get(sid)
        stock_forecasts = forecasts.get(sid, {})
        report = latest_reports.get(sid)
        note = notes.get(sid)
        quote = quotes.get(stock.code, {})

        # 维度 3 · 护城河
        gross_margin = float(fund.gross_margin) if fund and fund.gross_margin is not None else None
        net_margin = float(fund.net_margin) if fund and fund.net_margin is not None else None
        roe = float(fund.roe) if fund and fund.roe is not None else None

        # 维度 4 · 估值
        pe_ttm = float(fund.pe_ttm) if fund and fund.pe_ttm is not None else None

        # 维度 5 · 业绩兑现
        revenue_yoy = float(fund.revenue_yoy) if fund and fund.revenue_yoy is not None else None
        profit_yoy = float(fund.profit_yoy) if fund and fund.profit_yoy is not None else None

        # 维度 6 · AI 报告
        overall_signal = report.overall_signal if report else None
        ai_conclusion = report.conclusion if report else None
        technical_score = report.technical_score if report else None
        fundamental_score = report.fundamental_score if report else None
        industry_inflection = report.industry_inflection if report else None
        external_disruption = report.external_disruption if report else None
        ai_action_suggestion = report.action_suggestion if report else None
        technical_analysis = None
        if report and report.full_report:
            technical_analysis = report.full_report.get("technical_analysis")

        # Claude「核心 + 6D + 技术」评分（2026-05 精简版,仅当 full_report.source == 'claude_chat' 时生效）
        claude_overall_score = None
        claude_industry_score = None       # D1' 行业拐点+叙事(合并)
        claude_disruption_score = None     # D2 外部颠覆
        claude_moat_score = None           # D3 护城河
        claude_valuation_score = None      # D4 动态赔率
        claude_performance_score = None    # D5' 业绩+财务(合并)
        claude_governance_score = None     # D8 治理
        claude_tech_score = None           # 技术评估(新增)
        claude_veto_triggered = None
        claude_veto_reason = None
        claude_overall_label = None
        claude_score_at = None
        if report and report.full_report and report.full_report.get("source") == "claude_chat":
            fr = report.full_report
            claude_overall_score = fr.get("claude_overall_score")
            claude_industry_score = fr.get("claude_industry_score")
            claude_disruption_score = fr.get("claude_disruption_score")
            claude_moat_score = fr.get("claude_moat_score")
            claude_valuation_score = fr.get("claude_valuation_score")
            claude_performance_score = fr.get("claude_performance_score")
            claude_governance_score = fr.get("claude_governance_score")
            claude_tech_score = fr.get("claude_tech_score")
            claude_veto_triggered = fr.get("veto_triggered")
            claude_veto_reason = fr.get("veto_reason")
            claude_overall_label = fr.get("claude_overall_label")
            claude_score_at = report.generated_at

        # v5 实时目标价信号(2026-05 新增,主决策因子)
        v5 = v5_map.get(sid)
        v5_final_score = float(v5.final_score) if v5 and v5.final_score is not None else None
        v5_base_score = float(v5.base_score) if v5 and v5.base_score is not None else None
        v5_upside_pct = float(v5.upside_pct) if v5 and v5.upside_pct is not None else None
        v5_avg_target_weighted = float(v5.avg_target_weighted) if v5 and v5.avg_target_weighted is not None else None
        v5_avg_target_simple = float(v5.avg_target_simple) if v5 and v5.avg_target_simple is not None else None
        v5_freshness_status = v5.freshness_status if v5 else None
        v5_research_count_30d = v5.research_count_30d if v5 else None
        v5_research_count_90d = v5.research_count_90d if v5 else None
        v5_has_consensus = v5.has_consensus if v5 else None
        v5_upgrade_count_30d = v5.upgrade_count_30d if v5 else None
        v5_veto_triggered = v5.veto_triggered if v5 else None
        v5_veto_reason = v5.veto_reason if v5 else None
        v5_updated_at = v5.updated_at if v5 else None

        # 财报临近 + 上次 surprise(2026-05 新增)
        upcoming_earnings_date = upcoming_earnings_map.get(sid)
        days_to_earnings = (upcoming_earnings_date - today).days if upcoming_earnings_date else None
        last_surprise = last_surprise_map.get(sid)
        last_earnings_surprise_direction = last_surprise.surprise_direction if last_surprise else None
        last_earnings_surprise_pct = (
            float(last_surprise.surprise_net_profit_pct)
            if last_surprise and last_surprise.surprise_net_profit_pct is not None
            else None
        )

        # 净利润预测（亿元），优先 manual > llm > tushare
        def _best_forecast(year: int) -> tuple[float | None, str | None]:
            pf = stock_forecasts.get(year)
            if pf and pf.net_profit_forecast is not None:
                return float(pf.net_profit_forecast) / 1e8, pf.source
            return None, None

        forecast_2026, src_2026 = _best_forecast(2026)
        forecast_2027, src_2027 = _best_forecast(2027)
        forecast_source = src_2026 or src_2027

        # 市值（亿元） = PE-TTM × 净利润-TTM
        market_cap = None
        if fund and fund.pe_ttm is not None and fund.net_profit is not None:
            try:
                market_cap = float(fund.pe_ttm) * float(fund.net_profit) / 1e8
            except Exception:
                pass

        # 远期PE
        def _forward_pe(np_forecast: float | None) -> float | None:
            if market_cap and np_forecast and np_forecast > 0:
                return round(market_cap / np_forecast, 1)
            return None

        forward_pe_2026 = _forward_pe(forecast_2026)
        forward_pe_2027 = _forward_pe(forecast_2027)

        # 实时行情
        current_price = quote.get("price") or quote.get("current") or None
        ytd_change = quote.get("ytd_change") or None

        # 若 Redis 无行情，从 K 线取价格和年初涨幅
        if current_price is None or ytd_change is None:
            try:
                import pandas as pd
                from app.services.kline_service import get_kline_dataframe
                klines = await get_kline_dataframe(db, stock.code, days=260)
                if not klines.empty:
                    last_close = float(klines["close"].iloc[-1])
                    if current_price is None:
                        current_price = last_close
                    if ytd_change is None:
                        year_start = str(date.today().year)
                        ytd_klines = klines[klines.index >= pd.Timestamp(f"{year_start}-01-01")]
                        if not ytd_klines.empty:
                            first_close = float(ytd_klines["close"].iloc[0])
                            if first_close:
                                ytd_change = round((last_close / first_close - 1) * 100, 2)
            except Exception:
                pass

        rows.append(
            WatchlistTableRow(
                code=stock.code,
                name=stock.name,
                market=stock.market,
                is_core=stock.is_core,
                gross_margin=gross_margin,
                net_margin=net_margin,
                roe=roe,
                pe_ttm=pe_ttm,
                forecast_2026=round(forecast_2026, 2) if forecast_2026 else None,
                forecast_2027=round(forecast_2027, 2) if forecast_2027 else None,
                forward_pe_2026=forward_pe_2026,
                forward_pe_2027=forward_pe_2027,
                revenue_yoy=revenue_yoy,
                profit_yoy=profit_yoy,
                overall_signal=overall_signal,
                ai_conclusion=ai_conclusion,
                technical_score=technical_score,
                fundamental_score=fundamental_score,
                technical_analysis=technical_analysis,
                industry_inflection=industry_inflection,
                external_disruption=external_disruption,
                ai_action_suggestion=ai_action_suggestion,
                current_price=current_price,
                ytd_change=ytd_change,
                recommendation=note.recommendation if note else None,
                personal_note=note.personal_note if note else None,
                market_cap=round(market_cap, 1) if market_cap else None,
                forecast_source=forecast_source,
                tags=[TagRead.model_validate(t) for t in tags_by_stock.get(sid, [])],
                claude_overall_score=claude_overall_score,
                claude_industry_score=claude_industry_score,
                claude_disruption_score=claude_disruption_score,
                claude_moat_score=claude_moat_score,
                claude_valuation_score=claude_valuation_score,
                claude_performance_score=claude_performance_score,
                claude_governance_score=claude_governance_score,
                claude_tech_score=claude_tech_score,
                claude_veto_triggered=claude_veto_triggered,
                claude_veto_reason=claude_veto_reason,
                claude_overall_label=claude_overall_label,
                claude_score_at=claude_score_at,
                upcoming_earnings_date=upcoming_earnings_date,
                days_to_earnings=days_to_earnings,
                last_earnings_surprise_direction=last_earnings_surprise_direction,
                last_earnings_surprise_pct=last_earnings_surprise_pct,
                v5_final_score=v5_final_score,
                v5_base_score=v5_base_score,
                v5_upside_pct=v5_upside_pct,
                v5_avg_target_weighted=v5_avg_target_weighted,
                v5_avg_target_simple=v5_avg_target_simple,
                v5_freshness_status=v5_freshness_status,
                v5_research_count_30d=v5_research_count_30d,
                v5_research_count_90d=v5_research_count_90d,
                v5_has_consensus=v5_has_consensus,
                v5_upgrade_count_30d=v5_upgrade_count_30d,
                v5_veto_triggered=v5_veto_triggered,
                v5_veto_reason=v5_veto_reason,
                v5_updated_at=v5_updated_at,
            )
        )

    return rows
