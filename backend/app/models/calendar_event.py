from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CalendarEvent(Base):
    """日历事件：财报披露日 / 解禁日 / 自定义提醒

    自选股之外的全市场也可入此表（stock_id 可为空，event_type='market_wide'）。
    detector 在 T-7 / T-1 触发 CALENDAR_REMINDER 事件。
    """
    __tablename__ = "calendar_events"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "event_type", "event_date",
            name="uq_calendar_stock_type_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int | None] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(
        Enum(
            "earnings_release", "restricted_release", "custom",
            "macro", "industry_conference",
            name="calendar_event_type_enum",
        ),
        nullable=False,
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock | None"] = relationship(back_populates="calendar_events")  # noqa: F821
