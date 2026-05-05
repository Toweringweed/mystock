"""detector 共用工具"""
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import StockEvent


async def upsert_event(
    db: AsyncSession,
    *,
    stock_id: int,
    event_type: str,
    severity: str,
    dedup_key: str,
    title: str,
    payload: dict | None = None,
    triggered_at: datetime | None = None,
) -> bool:
    """幂等写入事件。返回 True 表示新插入（rowcount>0）。"""
    stmt = pg_insert(StockEvent).values(
        stock_id=stock_id,
        event_type=event_type,
        severity=severity,
        dedup_key=dedup_key,
        title=title,
        payload=payload or {},
        triggered_at=triggered_at or datetime.now(),
    ).on_conflict_do_nothing(
        index_elements=["stock_id", "event_type", "dedup_key"]
    )
    result = await db.execute(stmt)
    return result.rowcount > 0
