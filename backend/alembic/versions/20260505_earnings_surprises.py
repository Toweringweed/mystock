"""create earnings_surprises table for tracking pre/post earnings expectations vs actuals

Revision ID: 20260505_earnings
Revises: 20260504_analyst
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260505_earnings"
down_revision = "20260504_analyst"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "earnings_surprises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # 期间标识
        sa.Column("period_type", sa.String(16), nullable=False),  # quarterly / annual
        sa.Column("period", sa.String(16), nullable=False),        # 2026Q1 / 2025
        sa.Column("release_date", sa.Date(), nullable=False),      # 实际披露日
        sa.Column("expected_release_date", sa.Date(), nullable=True),  # 预设披露日(从 calendar_events)

        # 一致预期(财报发布前)— 单位:亿元
        sa.Column("expected_revenue_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_net_profit_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("expected_eps", sa.Numeric(10, 4), nullable=True),
        sa.Column("expected_yoy_growth", sa.Numeric(8, 2), nullable=True),  # %
        sa.Column("expected_source", sa.String(64), nullable=True),  # 一致预期来源

        # 实际值(财报披露后)— 单位:亿元
        sa.Column("actual_revenue_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_net_profit_yi", sa.Numeric(12, 2), nullable=True),
        sa.Column("actual_eps", sa.Numeric(10, 4), nullable=True),
        sa.Column("actual_yoy_growth", sa.Numeric(8, 2), nullable=True),
        sa.Column("actual_qoq_growth", sa.Numeric(8, 2), nullable=True),  # 环比

        # Surprise 指标(% — (actual - expected) / expected × 100)
        sa.Column("surprise_revenue_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("surprise_net_profit_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "surprise_direction", sa.String(8), nullable=True,
        ),  # beat / meet / miss

        # 股价反应(%)
        sa.Column("price_at_release", sa.Numeric(12, 3), nullable=True),
        sa.Column("pre_release_5d_return", sa.Numeric(8, 2), nullable=True),
        sa.Column("pre_release_20d_return", sa.Numeric(8, 2), nullable=True),
        sa.Column("post_release_1d_return", sa.Numeric(8, 2), nullable=True),
        sa.Column("post_release_5d_return", sa.Numeric(8, 2), nullable=True),
        sa.Column("post_release_30d_return", sa.Numeric(8, 2), nullable=True),

        # 估值修正(发布前 vs 发布后机构 EPS 共识变动)
        sa.Column("forward_eps_revision_pct", sa.Numeric(8, 2), nullable=True),

        # 元数据
        sa.Column("data_source", sa.String(32), nullable=True),  # claude_chat / manual / auto_track
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
            "stock_id", "period_type", "period",
            name="uq_earnings_surprise_stock_period",
        ),
    )
    op.create_index(
        "ix_earnings_surprises_stock_release",
        "earnings_surprises",
        ["stock_id", sa.text("release_date DESC")],
    )
    op.create_index(
        "ix_earnings_surprises_release_date",
        "earnings_surprises",
        [sa.text("release_date DESC")],
    )
    op.create_index(
        "ix_earnings_surprises_direction",
        "earnings_surprises",
        ["surprise_direction"],
    )


def downgrade() -> None:
    op.drop_index("ix_earnings_surprises_direction", table_name="earnings_surprises")
    op.drop_index("ix_earnings_surprises_release_date", table_name="earnings_surprises")
    op.drop_index("ix_earnings_surprises_stock_release", table_name="earnings_surprises")
    op.drop_table("earnings_surprises")
