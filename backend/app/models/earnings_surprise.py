from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class EarningsSurprise(Base):
    """财报预期差跟踪 — 一致预期 vs 实际 vs 股价反应"""
    __tablename__ = "earnings_surprises"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "period_type", "period",
            name="uq_earnings_surprise_stock_period",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )

    # 期间
    period_type: Mapped[str] = mapped_column(String(16), nullable=False)  # quarterly / annual
    period: Mapped[str] = mapped_column(String(16), nullable=False)        # 2026Q1 / 2025
    release_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_release_date: Mapped[date | None] = mapped_column(Date)

    # 一致预期(亿元)
    expected_revenue_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    expected_net_profit_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    expected_eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    expected_yoy_growth: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    expected_source: Mapped[str | None] = mapped_column(String(64))

    # 实际值(亿元)
    actual_revenue_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_net_profit_yi: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    actual_eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    actual_yoy_growth: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    actual_qoq_growth: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    # Surprise
    surprise_revenue_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    surprise_net_profit_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    surprise_direction: Mapped[str | None] = mapped_column(String(8))  # beat/meet/miss

    # 股价反应
    price_at_release: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    pre_release_5d_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    pre_release_20d_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    post_release_1d_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    post_release_5d_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    post_release_30d_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    # 估值修正
    forward_eps_revision_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))

    # 元数据
    data_source: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
