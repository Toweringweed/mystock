"""create estimate_revisions table for tracking analyst EPS/target price revisions over time

Revision ID: 20260506_revisions
Revises: 20260505_earnings
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa

revision = "20260506_revisions"
down_revision = "20260505_earnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "estimate_revisions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # 时间标识
        sa.Column("revision_date", sa.Date(), nullable=False),  # 共识快照日(月底/季末)
        sa.Column("forecast_year", sa.Integer(), nullable=False),  # 预测年份(2026/2027)

        # 共识快照
        sa.Column("consensus_eps", sa.Numeric(10, 4), nullable=True),
        sa.Column("consensus_net_profit_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("consensus_revenue_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("consensus_target_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("institution_count", sa.Integer(), nullable=True),  # 覆盖机构数

        # 月度变化(与上一快照相比)
        sa.Column("eps_revision_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("net_profit_revision_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("target_price_revision_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "revision_direction", sa.String(8), nullable=True,
        ),  # up / flat / down

        # 元数据
        sa.Column("source", sa.String(32), nullable=True),  # ths / wind / manual / claude_chat
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),

        sa.UniqueConstraint(
            "stock_id", "revision_date", "forecast_year",
            name="uq_estimate_revision_stock_date_year",
        ),
    )
    op.create_index(
        "ix_estimate_revisions_stock_date",
        "estimate_revisions",
        ["stock_id", sa.text("revision_date DESC")],
    )
    op.create_index(
        "ix_estimate_revisions_direction",
        "estimate_revisions",
        ["revision_direction"],
    )


def downgrade() -> None:
    op.drop_index("ix_estimate_revisions_direction", table_name="estimate_revisions")
    op.drop_index("ix_estimate_revisions_stock_date", table_name="estimate_revisions")
    op.drop_table("estimate_revisions")
