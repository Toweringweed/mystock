from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockAlias(Base):
    """股票别名表

    用于资讯实体匹配：从 stocks.name 派生短名、用户手动添加、AI 提取的子公司/产品名。
    """
    __tablename__ = "stock_aliases"
    __table_args__ = (
        UniqueConstraint("stock_id", "alias", name="uq_stock_aliases_stock_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # short_name / english_name / subsidiary / product / manual / supply_chain
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="aliases")  # noqa: F821
