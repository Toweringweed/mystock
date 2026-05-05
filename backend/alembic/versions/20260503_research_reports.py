"""create research_report_meta extension table

Revision ID: 20260503_research
Revises: 20260502_tags
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa

revision = "20260503_research"
down_revision = "20260502_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_report_meta",
        sa.Column(
            "news_id", sa.Integer(),
            sa.ForeignKey("industry_news.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker", sa.String(64), nullable=False),
        sa.Column("rating", sa.String(16), nullable=True),
        sa.Column("forecast_year_base", sa.Integer(), nullable=True),
        sa.Column("eps_y1", sa.Numeric(10, 4), nullable=True),
        sa.Column("eps_y2", sa.Numeric(10, 4), nullable=True),
        sa.Column("eps_y3", sa.Numeric(10, 4), nullable=True),
        sa.Column("pe_y1", sa.Numeric(10, 2), nullable=True),
        sa.Column("pe_y2", sa.Numeric(10, 2), nullable=True),
        sa.Column("pe_y3", sa.Numeric(10, 2), nullable=True),
        sa.Column("pdf_url", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_research_meta_stock_id", "research_report_meta", ["stock_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_research_meta_stock_id", table_name="research_report_meta")
    op.drop_table("research_report_meta")
