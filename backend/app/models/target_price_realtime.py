from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockTargetPriceRealtime(Base):
    """v5 框架 — 实时目标价上行空间(主决策因子)"""
    __tablename__ = "stock_target_price_realtime"

    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True
    )

    current_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    avg_target_simple: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    avg_target_weighted: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    highest_target: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    lowest_target: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    target_dispersion_cv: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    upside_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    base_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    final_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))

    has_consensus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bonus_consensus_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    upgrade_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    bonus_revisions_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    total_bonus_pct: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))

    research_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    research_count_90d: Mapped[int] = mapped_column(Integer, default=0)
    days_since_latest: Mapped[int | None] = mapped_column(Integer)
    freshness_status: Mapped[str | None] = mapped_column(String(8))
    freshness_factor: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))

    veto_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    veto_reason: Mapped[str | None] = mapped_column(String(64))

    institution_breakdown: Mapped[dict | None] = mapped_column(JSONB)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
