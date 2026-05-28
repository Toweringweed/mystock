from datetime import datetime

from sqlalchemy import (
    BigInteger, DateTime, Float, ForeignKey, Integer, PrimaryKeyConstraint,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IndustryNews(Base):
    __tablename__ = "industry_news"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)          # AI 生成摘要（100字）
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sentiment: Mapped[str | None] = mapped_column(String(10))  # positive / negative / neutral
    related_industries: Mapped[list | None] = mapped_column(ARRAY(String))
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # SHA256 精确去重

    # ── Phase 1 新增：资讯流水线打分字段 ──────────────────────────────
    category: Mapped[str | None] = mapped_column(String(20))           # announcement / news / social / research
    source_authority: Mapped[float | None] = mapped_column(Float)      # 消息源权威度 0~1
    simhash: Mapped[int | None] = mapped_column(BigInteger, index=True)  # 64 位 SimHash 指纹（近似去重）
    direction: Mapped[str | None] = mapped_column(String(10))          # bullish / bearish / neutral
    urgency: Mapped[str | None] = mapped_column(String(10), index=True)  # urgent / important / info
    rule_score: Mapped[float | None] = mapped_column(Float)            # 规则层评分 0~1
    llm_score: Mapped[float | None] = mapped_column(Float)             # LLM 强度 1~5
    importance_score: Mapped[float | None] = mapped_column(Float, index=True)  # 综合分 0~1
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )  # 流水线处理时间，NULL = 待处理

    # ── P0 资讯升级新增 ──────────────────────────────────────────────
    # L0 规则识别的催化剂分类: merger/earnings/regulatory/contract/sanction/research/capacity/other
    catalyst_type: Mapped[str | None] = mapped_column(String(20), index=True)
    catalyst_summary: Mapped[str | None] = mapped_column(String(120))   # L1.5 LLM: 一句话催化剂(<=100 字)
    key_risks: Mapped[str | None] = mapped_column(String(240))          # L1.5 LLM: 关键风险(多条以 / 分隔)
    original_title: Mapped[str | None] = mapped_column(String(500))     # 英文资讯保留原文标题
    original_lang: Mapped[str | None] = mapped_column(String(5))        # en/zh/...
    l15_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stock_relations: Mapped[list["NewsStockRelation"]] = relationship(back_populates="news")


class NewsStockRelation(Base):
    __tablename__ = "news_stock_relations"
    __table_args__ = (
        PrimaryKeyConstraint("news_id", "stock_id"),
    )

    news_id: Mapped[int] = mapped_column(ForeignKey("industry_news.id"), nullable=False)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False)  # 0~1 相关度

    news: Mapped["IndustryNews"] = relationship(back_populates="stock_relations")
    stock: Mapped["Stock"] = relationship(back_populates="news_relations")  # noqa: F821
