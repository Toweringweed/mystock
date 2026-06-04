from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class InsiderTrade(Base):
    """股东减持/增持结构化记录（由 LLM 从公告标题/正文抽取）"""
    __tablename__ = "insider_trades"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "ann_date", "trade_type", "holder_name",
            name="uq_insider_stock_date_type_holder",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ann_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    trade_type: Mapped[str] = mapped_column(
        Enum("reduce", "increase", name="insider_trade_type_enum"),
        nullable=False,
    )
    holder_name: Mapped[str] = mapped_column(String(200), nullable=False)
    shares: Mapped[int | None] = mapped_column(BigInteger)
    amount: Mapped[float | None] = mapped_column(Numeric(20, 2))   # 金额（元）
    pct_of_total: Mapped[float | None] = mapped_column(Numeric(8, 4))  # 占总股本 %
    pct_before: Mapped[float | None] = mapped_column(Numeric(8, 4))
    pct_after: Mapped[float | None] = mapped_column(Numeric(8, 4))
    price_low: Mapped[float | None] = mapped_column(Numeric(12, 3))
    price_high: Mapped[float | None] = mapped_column(Numeric(12, 3))
    source_news_id: Mapped[int | None] = mapped_column(
        ForeignKey("industry_news.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="insider_trades")  # noqa: F821
