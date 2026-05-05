from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockFundamental(Base):
    __tablename__ = "stock_fundamentals"
    __table_args__ = (
        UniqueConstraint("stock_id", "period", "period_type", name="uq_fundamental_stock_period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(10), nullable=False)  # 如 "2024Q3" / "2024A"
    period_type: Mapped[str] = mapped_column(
        Enum("quarterly", "annual", "ttm", name="period_type_enum"), nullable=False
    )

    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2))       # 营收（元）
    net_profit: Mapped[float | None] = mapped_column(Numeric(20, 2))    # 净利润（元）
    eps: Mapped[float | None] = mapped_column(Numeric(10, 4))           # 每股收益
    pe_ttm: Mapped[float | None] = mapped_column(Numeric(10, 4))        # PE-TTM
    pb: Mapped[float | None] = mapped_column(Numeric(10, 4))            # PB
    ps: Mapped[float | None] = mapped_column(Numeric(10, 4))            # PS-TTM = market_cap / revenue_ttm
    roe: Mapped[float | None] = mapped_column(Numeric(8, 4))            # ROE %
    gross_margin: Mapped[float | None] = mapped_column(Numeric(8, 4))   # 毛利率 %
    net_margin: Mapped[float | None] = mapped_column(Numeric(8, 4))     # 净利率 %
    debt_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))     # 资产负债率 %
    current_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))   # 流动比率
    cash_flow_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4)) # 经营现金流/净利润
    revenue_yoy: Mapped[float | None] = mapped_column(Numeric(8, 4))     # 营收同比 %
    profit_yoy: Mapped[float | None] = mapped_column(Numeric(8, 4))      # 净利润同比 %

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="fundamentals")  # noqa: F821


class ProfitForecast(Base):
    __tablename__ = "profit_forecasts"
    __table_args__ = (
        UniqueConstraint("stock_id", "forecast_year", "source", name="uq_forecast_stock_year_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    forecast_year: Mapped[int] = mapped_column(Integer, nullable=False)
    eps_forecast: Mapped[float | None] = mapped_column(Numeric(10, 4))         # 预测EPS
    net_profit_forecast: Mapped[float | None] = mapped_column(Numeric(20, 2))  # 预测净利润（元）
    revenue_forecast: Mapped[float | None] = mapped_column(Numeric(20, 2))     # 预测营收（元）
    forward_pe: Mapped[float | None] = mapped_column(Numeric(10, 4))           # 远期PE（计算时的当前价格）
    source: Mapped[str] = mapped_column(String(50), nullable=False)            # tushare / eastmoney / manual
    analyst_count: Mapped[int | None] = mapped_column(Integer)                 # 覆盖分析师数量

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="forecasts")  # noqa: F821
