"""create stock_target_price_realtime table for v5 framework (target-price-driven)

Revision ID: 20260509_tprt
Revises: 20260508_qfinext
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260509_tprt"
down_revision = "20260508_qfinext"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_target_price_realtime",
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"),
                  primary_key=True),

        # 当前价 + 目标价
        sa.Column("current_price", sa.Numeric(12, 3)),
        sa.Column("avg_target_simple", sa.Numeric(12, 3)),         # 简单均值
        sa.Column("avg_target_weighted", sa.Numeric(12, 3)),        # 加权均值(机构权重)
        sa.Column("highest_target", sa.Numeric(12, 3)),
        sa.Column("lowest_target", sa.Numeric(12, 3)),
        sa.Column("target_dispersion_cv", sa.Numeric(8, 4)),         # std/mean

        # 上行空间(基于加权均值)
        sa.Column("upside_pct", sa.Numeric(8, 2)),                   # %
        sa.Column("base_score", sa.Numeric(4, 2)),                   # 1-10
        sa.Column("final_score", sa.Numeric(4, 2)),                  # 加成 + Veto 后

        # 加成
        sa.Column("has_consensus", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("bonus_consensus_pct", sa.Numeric(4, 2)),          # 0.20 或 0
        sa.Column("upgrade_count_30d", sa.Integer(), server_default="0"),
        sa.Column("bonus_revisions_pct", sa.Numeric(4, 2)),          # 0.40 或 0
        sa.Column("total_bonus_pct", sa.Numeric(4, 2)),              # 总加成

        # 时效
        sa.Column("research_count_30d", sa.Integer(), server_default="0"),
        sa.Column("research_count_90d", sa.Integer(), server_default="0"),
        sa.Column("days_since_latest", sa.Integer()),
        sa.Column("freshness_status", sa.String(8)),                 # fresh/recent/aging/stale/none
        sa.Column("freshness_factor", sa.Numeric(4, 2)),             # 1.0/0.85/0.6/0.3

        # Veto
        sa.Column("veto_triggered", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("veto_reason", sa.String(64)),

        # 透明化:各机构具体预测(JSONB)
        sa.Column("institution_breakdown", JSONB()),

        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_target_price_realtime_score",
        "stock_target_price_realtime",
        [sa.text("final_score DESC NULLS LAST")],
    )
    op.create_index(
        "ix_target_price_realtime_upside",
        "stock_target_price_realtime",
        [sa.text("upside_pct DESC NULLS LAST")],
    )


def downgrade() -> None:
    op.drop_index("ix_target_price_realtime_upside", table_name="stock_target_price_realtime")
    op.drop_index("ix_target_price_realtime_score", table_name="stock_target_price_realtime")
    op.drop_table("stock_target_price_realtime")
