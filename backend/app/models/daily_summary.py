from datetime import date, datetime

from sqlalchemy import (
    Boolean,
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


class DailySummary(Base):
    """每日 L1 摘要（Haiku 批量生成）

    每只自选股每天一行，作为"信号快照"。
    与 analysis_reports（Sonnet 深度报告）配合：
      - daily_summaries: 全部股每天一行，便宜，一句话
      - analysis_reports: 仅触发事件的股，深度报告
    """
    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("stock_id", "summary_date", name="uq_daily_summary"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(String(20))           # 5 字标签 e.g. "技术回调"
    one_liner: Mapped[str | None] = mapped_column(String(200))      # 一句话结论
    signal: Mapped[str | None] = mapped_column(
        Enum("bullish", "bearish", "neutral", name="signal_enum",
             create_type=False),  # 复用 analysis 模块定义的 enum
    )
    label_changed: Mapped[bool] = mapped_column(Boolean, default=False)
    model_used: Mapped[str | None] = mapped_column(String(50))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="daily_summaries")  # noqa: F821
