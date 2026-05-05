from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SupplyChain(Base):
    __tablename__ = "supply_chains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(
        Enum("upstream", "downstream", "competitor", name="supply_chain_type_enum"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_code: Mapped[str | None] = mapped_column(String(10))   # 如果是上市公司
    product_desc: Mapped[str | None] = mapped_column(Text)         # 供应/采购的产品/服务
    percentage: Mapped[float | None] = mapped_column(Numeric(6, 2)) # 占采购/销售比例 %
    importance: Mapped[str] = mapped_column(
        Enum("high", "medium", "low", name="importance_enum"),
        nullable=False,
        default="medium",
    )
    is_listed: Mapped[bool] = mapped_column(Boolean, default=False)
    data_source: Mapped[str] = mapped_column(String(50), default="annual_report_ai")
    report_year: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="supply_chains")  # noqa: F821
