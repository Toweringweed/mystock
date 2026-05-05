from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, UniqueConstraint, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockDailyKline(Base):
    __tablename__ = "stock_daily_kline"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_kline_stock_date"),
        Index("ix_kline_stock_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Numeric(12, 3))
    high: Mapped[float | None] = mapped_column(Numeric(12, 3))
    low: Mapped[float | None] = mapped_column(Numeric(12, 3))
    close: Mapped[float | None] = mapped_column(Numeric(12, 3))
    volume: Mapped[int | None] = mapped_column(BigInteger)          # 成交量（手）
    amount: Mapped[float | None] = mapped_column(Numeric(20, 2))    # 成交额（元）
    turnover: Mapped[float | None] = mapped_column(Numeric(8, 4))   # 换手率 %
    change_pct: Mapped[float | None] = mapped_column(Numeric(8, 4)) # 涨跌幅 %
    volume_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))  # 量比 = 当日量 / 5日均量
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="klines")  # noqa: F821


class StockTechnicalIndicator(Base):
    __tablename__ = "stock_technical_indicators"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_indicator_stock_date"),
        Index("ix_indicator_stock_date", "stock_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 移动平均
    ma5: Mapped[float | None] = mapped_column(Numeric(12, 3))
    ma10: Mapped[float | None] = mapped_column(Numeric(12, 3))
    ma20: Mapped[float | None] = mapped_column(Numeric(12, 3))
    ma60: Mapped[float | None] = mapped_column(Numeric(12, 3))

    # MACD (12,26,9)
    macd: Mapped[float | None] = mapped_column(Numeric(12, 6))
    macd_signal: Mapped[float | None] = mapped_column(Numeric(12, 6))
    macd_hist: Mapped[float | None] = mapped_column(Numeric(12, 6))

    # RSI
    rsi_6: Mapped[float | None] = mapped_column(Numeric(8, 4))
    rsi_14: Mapped[float | None] = mapped_column(Numeric(8, 4))
    rsi_24: Mapped[float | None] = mapped_column(Numeric(8, 4))

    # KDJ (9,3,3)
    kdj_k: Mapped[float | None] = mapped_column(Numeric(8, 4))
    kdj_d: Mapped[float | None] = mapped_column(Numeric(8, 4))
    kdj_j: Mapped[float | None] = mapped_column(Numeric(8, 4))

    # 布林带 (20,2)
    bb_upper: Mapped[float | None] = mapped_column(Numeric(12, 3))
    bb_middle: Mapped[float | None] = mapped_column(Numeric(12, 3))
    bb_lower: Mapped[float | None] = mapped_column(Numeric(12, 3))

    # OBV
    obv: Mapped[int | None] = mapped_column(BigInteger)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="indicators")  # noqa: F821
