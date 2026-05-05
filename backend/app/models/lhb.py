from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockLhb(Base):
    """龙虎榜（个股入选 + 买卖席位）"""
    __tablename__ = "stock_lhb"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_lhb_stock_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 上榜原因
    reason: Mapped[str | None] = mapped_column(String(200))
    # 总买入 / 总卖出（元）
    buy_amount: Mapped[float | None] = mapped_column(Numeric(20, 2))
    sell_amount: Mapped[float | None] = mapped_column(Numeric(20, 2))
    net_amount: Mapped[float | None] = mapped_column(Numeric(20, 2))
    # 当日涨跌幅 %
    change_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    # [{"name": "...", "buy_amount": ..., "sell_amount": ...}, ...]
    top_buyers: Mapped[list | None] = mapped_column(JSONB)
    top_sellers: Mapped[list | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="lhb_records")  # noqa: F821
