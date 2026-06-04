"""供应链分析 Celery 任务"""
import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.supply_chain_tasks.extract_supply_chain_task", bind=True, max_retries=2)
def extract_supply_chain_task(self, stock_code: str):
    """下载年报并 AI 提取供应链"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.supply_chain_service import SupplyChainService

        async with AsyncSessionLocal() as db:
            service = SupplyChainService()
            result = await service.extract_and_save(db, stock_code)
            await db.commit()
            logger.info(f"[{stock_code}] 供应链提取完成: {len(result)} 条关系")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[{stock_code}] 供应链提取失败: {exc}")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="app.tasks.supply_chain_tasks.extract_segments_for_all", bind=True, max_retries=1)
def extract_segments_for_all(self):
    """对所有自选股提取业务分部数据(SOTP 用)"""
    async def _run():
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.stock import Stock

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(Stock.code).where(Stock.is_watchlist.is_(True))
            )
            codes = [c for (c,) in rows.all()]
            for code in codes:
                extract_segments_task.delay(code)
            logger.info(f"[extract_segments_for_all] fan-out {len(codes)} 只股")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[extract_segments_for_all] 失败: {exc}")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="app.tasks.supply_chain_tasks.extract_segments_task", bind=True, max_retries=2)
def extract_segments_task(self, stock_code: str):
    """单只股票:下载年报 → 提取分部信息文本 → LLM 结构化 → 写 business_segments"""
    async def _run():
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from app.core.database import AsyncSessionLocal
        from app.models.business_segment import BusinessSegment
        from app.models.stock import Stock
        from app.services.ai_analyzer.business_segment_extractor import BusinessSegmentExtractor
        from app.services.data_fetcher.annual_report_fetcher import AnnualReportFetcher

        async with AsyncSessionLocal() as db:
            stock_row = await db.execute(
                select(Stock.id, Stock.name).where(Stock.code == stock_code)
            )
            row = stock_row.one_or_none()
            if not row:
                logger.error(f"[{stock_code}] stock 不存在")
                return
            stock_id, name = row

            fetcher = AnnualReportFetcher()
            text = await fetcher.fetch_segment_text(stock_code)
            if not text:
                logger.warning(f"[{stock_code}] 年报分部文本为空,跳过")
                return

            extractor = BusinessSegmentExtractor()
            period, segments = await extractor.extract(stock_code, name, text, db=db)
            if not segments:
                logger.warning(f"[{stock_code}] LLM 未提取出有效分部")
                return

            period = period or "latest"
            saved = 0
            for seg in segments:
                stmt = pg_insert(BusinessSegment).values(
                    stock_id=stock_id,
                    report_period=period,
                    segment_name=seg["segment_name"],
                    category=seg.get("category"),
                    revenue=seg.get("revenue"),
                    revenue_pct=seg.get("revenue_pct"),
                    profit=seg.get("profit"),
                    profit_pct=seg.get("profit_pct"),
                    gross_margin=seg.get("gross_margin"),
                    growth_yoy=seg.get("growth_yoy"),
                    description=seg.get("description"),
                    extracted_from=f"annual_report:{stock_code}",
                ).on_conflict_do_update(
                    index_elements=["stock_id", "report_period", "segment_name"],
                    set_={
                        "category": seg.get("category"),
                        "revenue": seg.get("revenue"),
                        "revenue_pct": seg.get("revenue_pct"),
                        "profit": seg.get("profit"),
                        "profit_pct": seg.get("profit_pct"),
                        "gross_margin": seg.get("gross_margin"),
                        "growth_yoy": seg.get("growth_yoy"),
                        "description": seg.get("description"),
                    },
                )
                await db.execute(stmt)
                saved += 1
            await db.commit()
            logger.info(f"[{stock_code}] 分部提取完成: {saved} 条 ({period})")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[{stock_code}] 分部提取失败: {exc}")
        raise self.retry(exc=exc, countdown=300)
