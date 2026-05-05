from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric,
    UniqueConstraint, func, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockCapitalFlow(Base):
    """北上资金日度（Hong Kong Stock Connect → A 股）"""
    __tablename__ = "stock_capital_flows"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_capflow_stock_date"),
        Index("ix_capflow_stock_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    # 净流入金额（元，正=买入多，负=卖出多）
    net_inflow: Mapped[float | None] = mapped_column(Numeric(20, 2))
    net_inflow_5d: Mapped[float | None] = mapped_column(Numeric(20, 2))
    net_inflow_20d: Mapped[float | None] = mapped_column(Numeric(20, 2))
    # 持股占流通比 %
    shareholding_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))
    # 北上累计持股数（股）
    shareholding_volume: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="capital_flows")  # noqa: F821
