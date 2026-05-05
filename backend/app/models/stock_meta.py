from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class StockNote(Base):
    """用户对股票的备注：操作建议、自定义净利润预测覆盖等"""
    __tablename__ = "stock_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stock_id: Mapped[int] = mapped_column(
        ForeignKey("stocks.id"), nullable=False, unique=True, index=True
    )
    recommendation: Mapped[str | None] = mapped_column(Text)  # 操作建议（用户编辑）
    personal_note: Mapped[str | None] = mapped_column(Text)   # 个人笔记（用户自由文本）

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    stock: Mapped["Stock"] = relationship(back_populates="note")  # noqa: F821
