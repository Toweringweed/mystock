from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AnalystReport(Base):
    """券商/外资研报(Skill 自动写入,与 research_report_meta 互补:本表不依赖 industry_news)"""
    __tablename__ = "analyst_reports"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "institution", "report_date",
            name="uq_analyst_report_stock_inst_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    institution: Mapped[str] = mapped_column(String(64), nullable=False)
    is_foreign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)

    rating: Mapped[str | None] = mapped_column(String(16))
    coverage_type: Mapped[str | None] = mapped_column(String(16))  # initial/maintain/upgrade/downgrade

    target_price_a: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))   # A 股目标价(元)
    target_price_h: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))   # H 股目标价(港元)

    forecast_year_base: Mapped[int | None] = mapped_column(Integer)
    net_profit_y1: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))    # 亿元
    net_profit_y2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    net_profit_y3: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    eps_y1: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    eps_y2: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    eps_y3: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    pe_y1: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pe_y2: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pe_y3: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))

    summary: Mapped[str | None] = mapped_column(Text)
    key_points: Mapped[list | None] = mapped_column(JSONB)
    source_url: Mapped[str | None] = mapped_column(String(500))
    model_used: Mapped[str | None] = mapped_column(String(32))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    stock: Mapped["Stock"] = relationship()  # noqa: F821
