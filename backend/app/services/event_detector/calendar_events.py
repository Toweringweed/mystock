"""日历事件提醒

每日 16:15 在 run_event_detection 中调用：
  - 距事件 7 天   → CALENDAR_REMINDER (severity=medium)
  - 距事件 1 天   → CALENDAR_REMINDER (severity=high)
"""
import logging
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar_event import CalendarEvent
from app.models.stock import Stock
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)

LEAD_TIMES = [
    (7, "medium"),
    (1, "high"),
]

EVENT_LABEL = {
    "earnings_release": "财报披露",
    "restricted_release": "限售解禁",
    "macro": "宏观事件",
    "industry_conference": "行业会议",
    "custom": "自定义",
}


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    target = target_date or date.today()
    created = 0
    for lead_days, severity in LEAD_TIMES:
        target_event_date = target + timedelta(days=lead_days)
        rows = await db.execute(
            select(CalendarEvent)
            .where(CalendarEvent.event_date == target_event_date)
            .where(or_(
                CalendarEvent.stock_id.is_(None),  # 全市场事件
                CalendarEvent.stock_id.in_(
                    select(Stock.id).where(Stock.is_watchlist.is_(True))
                ),
            ))
        )
        for ev in rows.scalars().all():
            label = EVENT_LABEL.get(ev.event_type, ev.event_type)
            stock_id = ev.stock_id or 0  # 0 用作"全市场"占位（upsert_event 要求 stock_id）
            if stock_id == 0:
                # 全市场事件：跳过 stock_events 写入（事件流水以个股为主）
                continue
            ok = await upsert_event(
                db,
                stock_id=stock_id,
                event_type="CALENDAR_REMINDER",
                severity=severity,
                dedup_key=f"{ev.event_type}:{ev.event_date.isoformat()}:T-{lead_days}",
                title=f"[T-{lead_days}天] {label}：{ev.title}",
                payload={
                    "calendar_event_id": ev.id,
                    "calendar_event_type": ev.event_type,
                    "event_date": ev.event_date.isoformat(),
                    "lead_days": lead_days,
                    "raw_payload": ev.payload,
                },
            )
            if ok:
                created += 1
    return created
