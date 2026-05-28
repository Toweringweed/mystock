from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True, index=True)
    market: Mapped[str] = mapped_column(
        Enum("A", "HK", name="market_enum"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(50))
    sector: Mapped[str | None] = mapped_column(String(50))
    is_watchlist: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False, index=True, server_default="false")
    data_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    sync_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle", server_default="idle", index=True
    )
    sync_task_id: Mapped[str | None] = mapped_column(String(64))
    sync_error: Mapped[str | None] = mapped_column(Text)
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # 关系
    klines: Mapped[list["StockDailyKline"]] = relationship(back_populates="stock")  # noqa: F821
    indicators: Mapped[list["StockTechnicalIndicator"]] = relationship(back_populates="stock")  # noqa: F821
    fundamentals: Mapped[list["StockFundamental"]] = relationship(back_populates="stock")  # noqa: F821
    forecasts: Mapped[list["ProfitForecast"]] = relationship(back_populates="stock")  # noqa: F821
    chip_distributions: Mapped[list["ChipDistribution"]] = relationship(back_populates="stock")  # noqa: F821
    divergence_signals: Mapped[list["DivergenceSignal"]] = relationship(back_populates="stock")  # noqa: F821
    supply_chains: Mapped[list["SupplyChain"]] = relationship(back_populates="stock")  # noqa: F821
    reports: Mapped[list["AnalysisReport"]] = relationship(back_populates="stock")  # noqa: F821
    news_relations: Mapped[list["NewsStockRelation"]] = relationship(back_populates="stock")  # noqa: F821
    note: Mapped["StockNote | None"] = relationship(back_populates="stock", uselist=False)  # noqa: F821
    aliases: Mapped[list["StockAlias"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    events: Mapped[list["StockEvent"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    daily_summaries: Mapped[list["DailySummary"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    capital_flows: Mapped[list["StockCapitalFlow"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    lhb_records: Mapped[list["StockLhb"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    insider_trades: Mapped[list["InsiderTrade"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    calendar_events: Mapped[list["CalendarEvent"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    business_segments: Mapped[list["BusinessSegment"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
    tag_links: Mapped[list["StockTag"]] = relationship(back_populates="stock", cascade="all, delete-orphan")  # noqa: F821
