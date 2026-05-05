"""AI 信号方向翻转事件

  AI_SIGNAL_FLIP : 今日 daily_summaries.signal 与昨日不同（且都非 NULL）

需在 summary_generator 写完当日数据后再跑。
"""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_summary import DailySummary
from app.models.stock import Stock
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    target = target_date or date.today()
    yesterday = target - timedelta(days=1)

    today_rows = await db.execute(
        select(DailySummary, Stock.code, Stock.name)
        .join(Stock, Stock.id == DailySummary.stock_id)
        .where(DailySummary.summary_date == target)
        .where(DailySummary.signal.is_not(None))
    )
    today_map: dict[int, tuple[DailySummary, str, str]] = {
        d.stock_id: (d, code, name) for d, code, name in today_rows.all()
    }

    if not today_map:
        return 0

    yest_rows = await db.execute(
        select(DailySummary.stock_id, DailySummary.signal)
        .where(DailySummary.summary_date == yesterday)
        .where(DailySummary.stock_id.in_(today_map.keys()))
    )
    yest_signals: dict[int, str] = {sid: sig for sid, sig in yest_rows.all() if sig}

    created = 0
    for stock_id, (today_d, code, name) in today_map.items():
        prev_signal = yest_signals.get(stock_id)
        if not prev_signal or prev_signal == today_d.signal:
            continue
        title = (
            f"{name}({code}) AI 信号 {prev_signal} → {today_d.signal} | "
            f"{today_d.label or '—'}"
        )
        ok = await upsert_event(
            db,
            stock_id=stock_id,
            event_type="AI_SIGNAL_FLIP",
            severity="high",
            dedup_key=f"flip:{target.isoformat()}",
            title=title,
            payload={
                "summary_date": target.isoformat(),
                "from_signal": prev_signal,
                "to_signal": today_d.signal,
                "label": today_d.label,
                "one_liner": today_d.one_liner,
            },
        )
        if ok:
            created += 1
    return created
