from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class BusinessSegment(Base):
    """业务分部数据(供 SOTP 拆解估值用)

    从年报"分部信息"章节用 LLM 结构化提取。
    每个 (stock_id, report_period, segment_name) 唯一。

    `category` 枚举:
      - core      : 核心主业(如潍柴的"重卡发动机+整车")
      - legacy    : 传统/已并表海外业务(如潍柴的 KION)
      - growth    : 已落地的成长业务(如潍柴的"数据中心柴发")
      - option    : 期权/未量产业务(如潍柴的 "SOFC 燃料电池")
    SOTP 加权时不同 category 适用不同 PE 锚。
    """
    __tablename__ = "business_segments"
    __table_args__ = (
        UniqueConstraint(
            "stock_id", "report_period", "segment_name",
            name="uq_segment_stock_period_name",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    report_period: Mapped[str] = mapped_column(String(20), nullable=False)
    # e.g. "2025A" / "2025H1" / "2025Q3"
    segment_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(
        Enum("core", "legacy", "growth", "option",
             name="business_segment_category_enum"),
    )
    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2))         # 元
    revenue_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))       # 占比 %
    profit: Mapped[float | None] = mapped_column(Numeric(20, 2))           # 元(可空,有些公司只披露营收)
    profit_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))        # %
    gross_margin: Mapped[float | None] = mapped_column(Numeric(8, 4))      # %
    growth_yoy: Mapped[float | None] = mapped_column(Numeric(8, 4))        # %, 同比增速
    description: Mapped[str | None] = mapped_column(Text)
    extracted_from: Mapped[str | None] = mapped_column(String(500))        # PDF 文件名/URL
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="business_segments")  # noqa: F821
