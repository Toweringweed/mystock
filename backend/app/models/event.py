from datetime import datetime

from sqlalchemy import (
    DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockEvent(Base):
    """事件流水表

    所有 detector 检测到的异常事件（技术信号、估值异常、资讯、AI 信号翻转等）统一入此表。
    `dedup_key` 与 (stock_id, event_type) 组成唯一约束，保证幂等。

    event_type 取值（与 event_detector 模块对应）：
      - MACD_DIVERGENCE_NEW   : 当日新增 MACD 顶/底背离
      - VOLUME_SPIKE          : 异常放量（>20日均量×3）
      - PE_EXTREME_LOW        : PE-TTM 跌破 5 年 5% 分位
      - PE_EXTREME_HIGH       : PE-TTM 突破 5 年 95% 分位
      - URGENT_NEWS           : 紧急级资讯命中自选股
      - AI_SIGNAL_FLIP        : 今日 daily_summary.signal 与昨日不同
    """
    __tablename__ = "stock_events"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "event_type", "dedup_key",
            name="uq_event_stock_type_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", name="event_severity_enum"),
        nullable=False, default="medium",
    )
    dedup_key: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="events")  # noqa: F821
