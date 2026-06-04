"""AI 分析报告查询服务"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import AnalysisReport
from app.models.stock import Stock


async def _get_stock_id(db: AsyncSession, code: str) -> int | None:
    result = await db.execute(select(Stock.id).where(Stock.code == code))
    return result.scalar_one_or_none()


async def get_latest_report(db: AsyncSession, code: str) -> AnalysisReport | None:
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return None
    result = await db.execute(
        select(AnalysisReport)
        .where(AnalysisReport.stock_id == stock_id)
        .order_by(AnalysisReport.generated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_report_history(
    db: AsyncSession, code: str, limit: int = 30
) -> list[AnalysisReport]:
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return []
    result = await db.execute(
        select(AnalysisReport)
        .where(AnalysisReport.stock_id == stock_id)
        .order_by(AnalysisReport.generated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
