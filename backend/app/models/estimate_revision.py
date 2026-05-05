from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EstimateRevision(Base):
    """分析师月度 EPS / 目标价共识修正快照"""
    __tablename__ = "estimate_revisions"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "revision_date", "forecast_year",
            name="uq_estimate_revision_stock_date_year",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )

    revision_date: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)

    consensus_eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    consensus_net_profit_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    consensus_revenue_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    consensus_target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    institution_count: Mapped[int | None] = mapped_column(Integer)

    eps_revision_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    net_profit_revision_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    target_price_revision_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    revision_direction: Mapped[str | None] = mapped_column(String(8))  # up / flat / down

    source: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
