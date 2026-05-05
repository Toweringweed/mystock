from datetime import datetime

from sqlalchemy import (
    DateTime, ForeignKey, Integer, Numeric, String, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResearchReportMeta(Base):
    """券商研报扩展信息（与 IndustryNews 一对一，主信息见 IndustryNews）"""
    __tablename__ = "research_report_meta"

    news_id: Mapped[int] = mapped_column(
        ForeignKey("industry_news.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    broker: Mapped[str] = mapped_column(String(64), nullable=False)
    rating: Mapped[str | None] = mapped_column(String(16))

    forecast_year_base: Mapped[int | None] = mapped_column(Integer)
    eps_y1: Mapped[float | None] = mapped_column(Numeric(10, 4))
    eps_y2: Mapped[float | None] = mapped_column(Numeric(10, 4))
    eps_y3: Mapped[float | None] = mapped_column(Numeric(10, 4))
    pe_y1: Mapped[float | None] = mapped_column(Numeric(10, 2))
    pe_y2: Mapped[float | None] = mapped_column(Numeric(10, 2))
    pe_y3: Mapped[float | None] = mapped_column(Numeric(10, 2))

    pdf_url: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    news: Mapped["IndustryNews"] = relationship()  # noqa: F821
    stock: Mapped["Stock"] = relationship()  # noqa: F821
