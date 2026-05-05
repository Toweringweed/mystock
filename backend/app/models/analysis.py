from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Enum, Float, ForeignKey,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DivergenceSignal(Base):
    __tablename__ = "divergence_signals"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "signal_type", "detected_date",
            name="uq_divergence_stock_type_date",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    detected_date: Mapped[date] = mapped_column(Date, nullable=False)
    # 信号类型: MACD_BULL / MACD_BEAR / RSI_BULL / RSI_BEAR
    signal_type: Mapped[str] = mapped_column(String(20), nullable=False)
    price_point1: Mapped[float | None] = mapped_column(Numeric(12, 3))    # 第一个极值点价格
    price_point2: Mapped[float | None] = mapped_column(Numeric(12, 3))    # 第二个极值点价格
    indicator_point1: Mapped[float | None] = mapped_column(Numeric(12, 6))
    indicator_point2: Mapped[float | None] = mapped_column(Numeric(12, 6))
    confidence: Mapped[float | None] = mapped_column(Float)               # 0.0 ~ 1.0
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)    # 事后验证是否有效
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="divergence_signals")  # noqa: F821


class ChipDistribution(Base):
    __tablename__ = "chip_distributions"
    __table_args__ = (
        UniqueConstraint("stock_id", "calc_date", name="uq_chip_stock_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    calc_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_ranges: Mapped[dict] = mapped_column(JSONB)        # [{price_low, price_high, chip_pct}]
    profit_ratio: Mapped[float | None] = mapped_column(Float)   # 获利盘比例 0~1
    avg_cost: Mapped[float | None] = mapped_column(Numeric(12, 3))  # 平均成本
    concentration: Mapped[float | None] = mapped_column(Float)     # 筹码集中度
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="chip_distributions")  # noqa: F821


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(
        Enum("daily", "event_driven", "initial", name="report_type_enum"),
        nullable=False,
        default="daily",
    )
    conclusion: Mapped[str | None] = mapped_column(Text)             # 综合结论(2026-05 6D 升级:扩为 TEXT 容纳 100-300 字)
    overall_signal: Mapped[str | None] = mapped_column(
        Enum("bullish", "bearish", "neutral", name="signal_enum")
    )
    technical_score: Mapped[int | None] = mapped_column(Integer)     # 1~10
    fundamental_score: Mapped[int | None] = mapped_column(Integer)   # 1~10
    # 言简意赅的三段结论（AI 每次分析必填，用于首页/详情页直接展示）
    industry_inflection: Mapped[str | None] = mapped_column(String(160))  # 行业需求拐点
    external_disruption: Mapped[str | None] = mapped_column(String(160))  # 外部颠覆力量
    action_suggestion: Mapped[str | None] = mapped_column(Text)           # AI 操作建议(2026-05 扩容)
    full_report: Mapped[dict] = mapped_column(JSONB)                 # 完整报告 JSON
    model_used: Mapped[str | None] = mapped_column(String(50))
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="reports")  # noqa: F821
