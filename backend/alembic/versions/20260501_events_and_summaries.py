"""create stock_events and daily_summaries

Revision ID: 20260501_events
Revises: 20260430_news_pipeline
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260501_events"
down_revision = "20260430_news_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── stock_events ─────────────────────────────────────────────
    event_severity = sa.Enum(
        "low", "medium", "high",
        name="event_severity_enum",
        create_type=True,
    )
    op.create_table(
        "stock_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("severity", event_severity, nullable=False, server_default="medium"),
        sa.Column("dedup_key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "triggered_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "event_type", "dedup_key",
            name="uq_event_stock_type_dedup",
        ),
    )
    op.create_index("ix_stock_events_stock_id", "stock_events", ["stock_id"])
    op.create_index("ix_stock_events_event_type", "stock_events", ["event_type"])
    op.create_index("ix_stock_events_triggered_at", "stock_events", ["triggered_at"])

    # ── daily_summaries ──────────────────────────────────────────
    # signal_enum 已存在（analysis_reports 创建过）；用 dialect 版 ENUM 才能正确跳过 CREATE TYPE
    from sqlalchemy.dialects import postgresql
    signal_enum = postgresql.ENUM(
        "bullish", "bearish", "neutral",
        name="signal_enum",
        create_type=False,
    )
    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("label", sa.String(20), nullable=True),
        sa.Column("one_liner", sa.String(200), nullable=True),
        sa.Column("signal", signal_enum, nullable=True),
        sa.Column(
            "label_changed", sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint("stock_id", "summary_date", name="uq_daily_summary"),
    )
    op.create_index("ix_daily_summaries_stock_id", "daily_summaries", ["stock_id"])
    op.create_index("ix_daily_summaries_summary_date", "daily_summaries", ["summary_date"])


def downgrade() -> None:
    op.drop_index("ix_daily_summaries_summary_date", table_name="daily_summaries")
    op.drop_index("ix_daily_summaries_stock_id", table_name="daily_summaries")
    op.drop_table("daily_summaries")

    op.drop_index("ix_stock_events_triggered_at", table_name="stock_events")
    op.drop_index("ix_stock_events_event_type", table_name="stock_events")
    op.drop_index("ix_stock_events_stock_id", table_name="stock_events")
    op.drop_table("stock_events")

    sa.Enum(name="event_severity_enum").drop(op.get_bind(), checkfirst=True)
