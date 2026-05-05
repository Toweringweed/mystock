"""事件检测编排器"""
import asyncio
import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.event_detector import (
    calendar_events,
    insider_events,
    news_events,
    signal_flip_events,
    technical_events,
    valuation_events,
)

logger = logging.getLogger(__name__)


async def run_daily_detection(db: AsyncSession, target_date: date | None = None) -> dict[str, int]:
    """跑 technical / valuation / news 三类 detector。

    注：三类共用同一个 AsyncSession，不能并行跑（asyncpg 不允许同 conn 并发）。
    顺序执行；若未来切到独立连接，可以改 asyncio.gather。
    """
    counts = {
        "technical": await technical_events.detect_all(db, target_date),
        "valuation": await valuation_events.detect_all(db, target_date),
        "news": await news_events.detect_all(db, target_date),
        "insider": await insider_events.detect_all(db, target_date),
        "calendar": await calendar_events.detect_all(db, target_date),
    }
    await db.flush()
    logger.info(f"[event_detector] 检测完成: {counts}")
    return counts


async def detect_signal_flip(db: AsyncSession, target_date: date | None = None) -> int:
    n = await signal_flip_events.detect_all(db, target_date)
    await db.flush()
    logger.info(f"[event_detector] signal_flip 新增 {n} 条")
    return n
