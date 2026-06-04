from datetime import datetime

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndustryMetric(Base):
    """行业景气数据点（半导体/AI/算力相关 Tier 1 信号）

    示例：
      ("nvda_datacenter_revenue", "2026Q1", 25.5, "USD_billion", "10-Q")
      ("googl_capex_guidance", "2026Q2", 18.0, "USD_billion", "earnings_call")
    """
    __tablename__ = "industry_metrics"
    __table_args__ = (
        UniqueConstraint(
            "metric_name", "period", "source",
            name="uq_industry_metric_period_source",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # 财季或月份，如 "2026Q1" / "2026-04"
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    value: Mapped[float | None] = mapped_column(Numeric(20, 4))
    unit: Mapped[str | None] = mapped_column(String(40))   # USD_billion / RMB_billion / TB / count / pct
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # 10-Q / earnings_call / press_release
    extracted_from: Mapped[str | None] = mapped_column(String(500))   # PDF URL or filename
    extracted_quote: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
