"""全量股票列表缓存（用于本地搜索，避免每次联网调用 AKShare）"""
from datetime import datetime

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockUniverse(Base):
    __tablename__ = "stock_universe"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    market: Mapped[str] = mapped_column(String(2), nullable=False)  # "A" | "HK"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_stock_universe_name", "name"),
        Index("ix_stock_universe_market", "market"),
    )
