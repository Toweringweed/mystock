"""add catalyst/risks/original_title/original_lang to industry_news for P0 news upgrade

Revision ID: 20260514_news_p0
Revises: 20260513_is_core
Create Date: 2026-05-07

P0 资讯升级:
- catalyst_type:L0 规则识别的催化剂分类(M&A/earnings/regulatory/contract/sanction/research/capacity/other)
- catalyst_summary:L1.5 LLM 抽取的一句话催化剂描述(<=100 字)
- key_risks:L1.5 LLM 抽取的关键风险(<=200 字,多条以 / 分隔)
- original_title / original_lang:英文资讯保留原文标题 + 语言标识
- l15_extracted_at:L1.5 抽取时间戳,避免重复调 LLM
"""
import sqlalchemy as sa
from alembic import op


revision = "20260514_news_p0"
down_revision = "20260513_is_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("industry_news", sa.Column("catalyst_type", sa.String(20), nullable=True))
    op.add_column("industry_news", sa.Column("catalyst_summary", sa.String(120), nullable=True))
    op.add_column("industry_news", sa.Column("key_risks", sa.String(240), nullable=True))
    op.add_column("industry_news", sa.Column("original_title", sa.String(500), nullable=True))
    op.add_column("industry_news", sa.Column("original_lang", sa.String(5), nullable=True))
    op.add_column(
        "industry_news",
        sa.Column("l15_extracted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_industry_news_catalyst_type", "industry_news", ["catalyst_type"])


def downgrade() -> None:
    op.drop_index("ix_industry_news_catalyst_type", table_name="industry_news")
    op.drop_column("industry_news", "l15_extracted_at")
    op.drop_column("industry_news", "original_lang")
    op.drop_column("industry_news", "original_title")
    op.drop_column("industry_news", "key_risks")
    op.drop_column("industry_news", "catalyst_summary")
    op.drop_column("industry_news", "catalyst_type")
