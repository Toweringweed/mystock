"""add stock sync status fields

Revision ID: 20260515_stock_sync_status
Revises: 20260514_news_p0
Create Date: 2026-05-13
"""
import sqlalchemy as sa
from alembic import op


revision = "20260515_stock_sync_status"
down_revision = "20260514_news_p0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stocks",
        sa.Column("sync_status", sa.String(20), nullable=False, server_default="idle"),
    )
    op.add_column("stocks", sa.Column("sync_task_id", sa.String(64), nullable=True))
    op.add_column("stocks", sa.Column("sync_error", sa.Text(), nullable=True))
    op.add_column("stocks", sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stocks", sa.Column("sync_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_stocks_sync_status", "stocks", ["sync_status"])

    op.execute(
        """
        UPDATE stocks
        SET sync_status = CASE
            WHEN data_ready IS TRUE THEN 'ready'
            WHEN is_watchlist IS TRUE THEN 'pending'
            ELSE 'idle'
        END
        """
    )


def downgrade() -> None:
    op.drop_index("ix_stocks_sync_status", table_name="stocks")
    op.drop_column("stocks", "sync_completed_at")
    op.drop_column("stocks", "sync_started_at")
    op.drop_column("stocks", "sync_error")
    op.drop_column("stocks", "sync_task_id")
    op.drop_column("stocks", "sync_status")
