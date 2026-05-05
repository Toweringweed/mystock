"""create analyst_reports table for foreign/domestic analyst report ingestion

Revision ID: 20260504_analyst
Revises: 20260503_research
Create Date: 2026-05-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260504_analyst"
down_revision = "20260503_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analyst_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("institution", sa.String(64), nullable=False),
        sa.Column(
            "is_foreign", sa.Boolean(), nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("rating", sa.String(16), nullable=True),
        sa.Column("coverage_type", sa.String(16), nullable=True),
        sa.Column("target_price_a", sa.Numeric(10, 2), nullable=True),
        sa.Column("target_price_h", sa.Numeric(10, 2), nullable=True),
        sa.Column("forecast_year_base", sa.Integer(), nullable=True),
        sa.Column("net_profit_y1", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_profit_y2", sa.Numeric(12, 2), nullable=True),
        sa.Column("net_profit_y3", sa.Numeric(12, 2), nullable=True),
        sa.Column("eps_y1", sa.Numeric(10, 4), nullable=True),
        sa.Column("eps_y2", sa.Numeric(10, 4), nullable=True),
        sa.Column("eps_y3", sa.Numeric(10, 4), nullable=True),
        sa.Column("pe_y1", sa.Numeric(10, 2), nullable=True),
        sa.Column("pe_y2", sa.Numeric(10, 2), nullable=True),
        sa.Column("pe_y3", sa.Numeric(10, 2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_points", JSONB(), nullable=True),
        sa.Column("source_url", sa.String(500), nullable=True),
        sa.Column("model_used", sa.String(32), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "institution", "report_date",
            name="uq_analyst_report_stock_inst_date",
        ),
    )
    op.create_index(
        "ix_analyst_reports_stock_date",
        "analyst_reports",
        ["stock_id", sa.text("report_date DESC")],
    )
    op.create_index(
        "ix_analyst_reports_is_foreign",
        "analyst_reports",
        ["is_foreign"],
    )


def downgrade() -> None:
    op.drop_index("ix_analyst_reports_is_foreign", table_name="analyst_reports")
    op.drop_index("ix_analyst_reports_stock_date", table_name="analyst_reports")
    op.drop_table("analyst_reports")
