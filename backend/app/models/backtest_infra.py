"""回测基础设施 ORM(5 张表合并文件,因模型相对简单)"""
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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockDailyFactor(Base):
    __tablename__ = "stock_daily_factors"
    __table_args__ = (UniqueConstraint("stock_id", "trade_date", name="uq_stock_daily_factors_stock_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    pe_ttm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pe_static: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    pb: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    ps: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    peg: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    market_cap_total: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    market_cap_circulating: Mapped[Decimal | None] = mapped_column(Numeric(16, 2))
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IndustryDailyIndex(Base):
    __tablename__ = "industry_daily_index"
    __table_args__ = (UniqueConstraint("index_code", "trade_date", name="uq_industry_index_code_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    index_code: Mapped[str] = mapped_column(String(16), nullable=False)
    index_name: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    close: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pe_median: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class QuarterlyFinancialsHistory(Base):
    __tablename__ = "quarterly_financials_history"
    __table_args__ = (UniqueConstraint("stock_id", "period_end", name="uq_qfin_stock_period"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(8), nullable=False)
    revenue_yi: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    net_profit_yi: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    net_profit_deducted_yi: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    eps: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    roe: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    roe_weighted: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    gross_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    net_margin: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    debt_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    cash_flow_to_profit: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    revenue_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    profit_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    profit_qoq: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    # D3 子项(2026-05 新增)
    roic: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    fcf_yi: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    fcf_to_revenue: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    # D7 子项(2026-05 新增)
    accounts_receivable_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    inventory_days: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    goodwill_yi: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    goodwill_to_equity_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    current_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    quick_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    source: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InstitutionMetadata(Base):
    __tablename__ = "institution_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name_en: Mapped[str | None] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    is_foreign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    weight_factor: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))
    track_record_alpha: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    track_record_n_samples: Mapped[int] = mapped_column(Integer, default=0)
    last_calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BacktestSnapshot(Base):
    __tablename__ = "backtest_snapshots"
    __table_args__ = (UniqueConstraint("stock_id", "anchor_date", "framework_version", name="uq_backtest_snap_stock_anchor"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    anchor_date: Mapped[date] = mapped_column(Date, nullable=False)
    d1_industry: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d2_disruption: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d3_moat: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d4_valuation: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d5_performance: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d6_narrative: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d7_financial: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d8_governance: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    d9_momentum: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    overall_8d: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    veto_triggered: Mapped[bool] = mapped_column(Boolean, default=False)
    price_at_anchor: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    pe_ttm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    fwd_pe_2026: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    profit_yoy: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    research_count_90d: Mapped[int | None] = mapped_column(Integer)
    upgrade_count_90d: Mapped[int | None] = mapped_column(Integer)
    avg_target_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    return_30d: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    return_60d: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    return_90d: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    return_120d: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    subscore_details: Mapped[dict | None] = mapped_column(JSONB)
    framework_version: Mapped[str | None] = mapped_column(String(16), default="8d_v2")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
