"""create business_segments table for SOTP analysis

Revision ID: 20260501_segments
Revises: 20260501_p1_indicators
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260501_segments"
down_revision = "20260501_p1_indicators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cat_enum = sa.Enum(
        "core", "legacy", "growth", "option",
        name="business_segment_category_enum",
        create_type=True,
    )
    op.create_table(
        "business_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("report_period", sa.String(20), nullable=False),
        sa.Column("segment_name", sa.String(100), nullable=False),
        sa.Column("category", cat_enum, nullable=True),
        sa.Column("revenue", sa.Numeric(20, 2), nullable=True),
        sa.Column("revenue_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("profit", sa.Numeric(20, 2), nullable=True),
        sa.Column("profit_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("gross_margin", sa.Numeric(8, 4), nullable=True),
        sa.Column("growth_yoy", sa.Numeric(8, 4), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extracted_from", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "report_period", "segment_name",
            name="uq_segment_stock_period_name",
        ),
    )
    op.create_index("ix_segment_stock_id", "business_segments", ["stock_id"])
    op.create_index("ix_segment_period", "business_segments", ["report_period"])


def downgrade() -> None:
    op.drop_index("ix_segment_period", table_name="business_segments")
    op.drop_index("ix_segment_stock_id", table_name="business_segments")
    op.drop_table("business_segments")
    sa.Enum(name="business_segment_category_enum").drop(op.get_bind(), checkfirst=True)
