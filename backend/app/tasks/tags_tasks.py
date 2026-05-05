"""股票标签 Celery 任务"""
import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.tags_tasks.extract_tags_task", bind=True, max_retries=2)
def extract_tags_task(self, stock_code: str):
    """根据公司特征 AI 生成标签"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.tags_service import extract_and_save

        async with AsyncSessionLocal() as db:
            saved = await extract_and_save(db, stock_code)
            await db.commit()
            logger.info(f"[{stock_code}] 标签提取完成: {len(saved)} 条")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[{stock_code}] 标签提取失败: {exc}")
        raise self.retry(exc=exc, countdown=300)
