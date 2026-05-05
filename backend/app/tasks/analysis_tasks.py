"""技术分析 + AI 报告 Celery 任务"""
import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.analysis_tasks.calc_all_indicators")
def calc_all_indicators():
    """每日收盘后批量计算所有自选股技术指标 + 量比"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_service import get_all_watchlist_codes
        from app.services.analysis.technical_analyzer import TechnicalAnalyzer
        from app.services.kline_service import update_volume_ratios

        async with AsyncSessionLocal() as db:
            codes = await get_all_watchlist_codes(db)
            analyzer = TechnicalAnalyzer()
            for code in codes:
                try:
                    saved = await analyzer.calc_and_save(db, code)
                    vr_updated = await update_volume_ratios(db, code)
                    await db.commit()
                    logger.info(
                        f"[{code}] 技术指标 {saved} 条 + 量比回填 {vr_updated} 行"
                    )
                except Exception as e:
                    logger.error(f"[{code}] 技术指标计算失败: {e}")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.analysis_tasks.run_event_detection")
def run_event_detection():
    """每日 16:15：技术 + 估值 + 资讯 三类事件检测，写 stock_events，立即推送 high"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.event_detector.detector import run_daily_detection
        from app.services.notifier import dispatcher
        from app.models.event import StockEvent

        async with AsyncSessionLocal() as db:
            counts = await run_daily_detection(db)
            logger.info(f"[run_event_detection] 完成: {counts}")

            cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=2)
            row = await db.execute(
                select(StockEvent)
                .where(StockEvent.severity == "high")
                .where(StockEvent.notified_at.is_(None))
                .where(StockEvent.triggered_at >= cutoff)
            )
            for event in row.scalars().all():
                try:
                    await dispatcher.dispatch_event(db, event)
                except Exception as e:
                    logger.error(f"[run_event_detection] 推送 event_id={event.id} 失败: {e}")
            await db.commit()

    asyncio.run(_run())


@celery_app.task(name="app.tasks.analysis_tasks.generate_daily_summaries")
def generate_daily_summaries():
    """每日 16:30：L1 Haiku 批量生成所有自选股 daily_summary，尾部检测 signal_flip"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.ai_analyzer.summary_generator import SummaryGenerator
        from app.services.event_detector.detector import detect_signal_flip
        from app.services.notifier import dispatcher
        from app.models.event import StockEvent

        async with AsyncSessionLocal() as db:
            generator = SummaryGenerator()
            n = await generator.generate_for_all(db)
            logger.info(f"[generate_daily_summaries] L1 写入 {n} 条")

            flips = await detect_signal_flip(db)

            if flips:
                cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=1)
                row = await db.execute(
                    select(StockEvent)
                    .where(StockEvent.event_type == "AI_SIGNAL_FLIP")
                    .where(StockEvent.notified_at.is_(None))
                    .where(StockEvent.triggered_at >= cutoff)
                )
                for event in row.scalars().all():
                    try:
                        await dispatcher.dispatch_event(db, event)
                    except Exception as e:
                        logger.error(f"[generate_daily_summaries] flip 推送失败 eid={event.id}: {e}")

            await db.commit()

    asyncio.run(_run())


@celery_app.task(name="app.tasks.analysis_tasks.generate_reports_for_events")
def generate_reports_for_events():
    """每日 16:45：仅给"今日有事件"的股票生成 L2 Sonnet 深度报告"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.models.event import StockEvent
        from app.models.stock import Stock

        async with AsyncSessionLocal() as db:
            today_start = datetime.combine(date.today(), time.min, tzinfo=timezone.utc)
            row = await db.execute(
                select(Stock.code).distinct()
                .join(StockEvent, StockEvent.stock_id == Stock.id)
                .where(StockEvent.triggered_at >= today_start)
                .where(Stock.is_watchlist.is_(True))
            )
            codes = [c for (c,) in row.all()]
            logger.info(f"[generate_reports_for_events] 今日有事件的股票 {len(codes)} 只")
            for code in codes:
                generate_report_task.delay(code, "event_driven")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.analysis_tasks.generate_report_task", bind=True, max_retries=2)
def generate_report_task(self, stock_code: str, report_type: str = "daily"):
    """生成单只股票 AI 分析报告（默认 Sonnet 4.6）"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.ai_analyzer.report_generator import ReportGenerator

        async with AsyncSessionLocal() as db:
            generator = ReportGenerator()
            report = await generator.generate(db, stock_code, report_type)
            await db.commit()
            logger.info(f"[{stock_code}] AI 报告生成完成: {report.overall_signal}")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[{stock_code}] 报告生成失败: {exc}")
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name="app.tasks.analysis_tasks.dispatch_event_queue")
def dispatch_event_queue():
    """每整点：聚合推送 medium 级事件队列"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.notifier import dispatcher

        async with AsyncSessionLocal() as db:
            n = await dispatcher.flush_event_queue(db)
            await db.commit()
            if n:
                logger.info(f"[dispatch_event_queue] 推送 {n} 条事件")

    asyncio.run(_run())
