from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
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


class SupplyChainCompany(Base):
    """供应链公司实体，用于跨自选股去重和资讯匹配。"""

    __tablename__ = "supply_chain_companies"
    __table_args__ = (
        UniqueConstraint("normalized_name", name="uq_supply_chain_company_normalized_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    stock_code: Mapped[str | None] = mapped_column(String(10), index=True)
    market: Mapped[str | None] = mapped_column(String(10))
    is_listed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    industry: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyChainCompanyAlias(Base):
    """供应链公司别名，解决简称、英文名、股票代码和历史名称匹配。"""

    __tablename__ = "supply_chain_company_aliases"
    __table_args__ = (
        UniqueConstraint("company_id", "alias", name="uq_supply_chain_company_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    alias_type: Mapped[str] = mapped_column(String(20), nullable=False, default="name")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyChainRelationship(Base):
    """证据化供应链关系边。source -> target 始终代表价值流/产品流方向。"""

    __tablename__ = "supply_chain_relationships"
    __table_args__ = (
        UniqueConstraint(
            "host_stock_id",
            "source_company_id",
            "target_company_id",
            "relation_type",
            "product_desc",
            name="uq_supply_chain_relationship",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host_stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    source_company_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_companies.id"), nullable=False, index=True
    )
    target_company_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_companies.id"), nullable=False, index=True
    )
    legacy_supply_chain_id: Mapped[int | None] = mapped_column(
        ForeignKey("supply_chains.id", ondelete="SET NULL"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    product_desc: Mapped[str | None] = mapped_column(Text)
    cooperation_desc: Mapped[str | None] = mapped_column(Text)
    percentage: Mapped[float | None] = mapped_column(Numeric(6, 2))
    importance: Mapped[str] = mapped_column(String(10), nullable=False, default="medium")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    chain_layer: Mapped[str | None] = mapped_column(String(20))
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="annual_report_ai")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyChainEvidence(Base):
    """供应链关系证据，保存来源和原文片段。"""

    __tablename__ = "supply_chain_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    relationship_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_relationships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_title: Mapped[str | None] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quote: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    meta: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyChainNewsLink(Base):
    """资讯与供应链公司/关系的匹配结果，用于图谱高亮和反向关联自选股。"""

    __tablename__ = "supply_chain_news_links"
    __table_args__ = (
        UniqueConstraint("news_id", "stock_id", "company_id", name="uq_supply_chain_news_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_id: Mapped[int] = mapped_column(
        ForeignKey("industry_news.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_companies.id"), nullable=False, index=True
    )
    relationship_id: Mapped[int | None] = mapped_column(
        ForeignKey("supply_chain_relationships.id", ondelete="SET NULL"), index=True
    )
    supply_chain_id: Mapped[int | None] = mapped_column(
        ForeignKey("supply_chains.id", ondelete="SET NULL"), index=True
    )
    matched_alias: Mapped[str] = mapped_column(String(120), nullable=False)
    relevance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    impact_direction: Mapped[str | None] = mapped_column(String(10))
    impact_summary: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SupplyChainEventImpact(Base):
    """供应链事件后验验证：预留股价联动统计字段。"""

    __tablename__ = "supply_chain_event_impacts"
    __table_args__ = (
        UniqueConstraint("news_link_id", "horizon_days", name="uq_supply_chain_event_impact"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    news_link_id: Mapped[int] = mapped_column(
        ForeignKey("supply_chain_news_links.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_return_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    benchmark_return_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    excess_return_pct: Mapped[float | None] = mapped_column(Numeric(8, 4))
    volume_ratio: Mapped[float | None] = mapped_column(Numeric(8, 4))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
