"""add is_core column to stocks for marking core watchlist subset

Revision ID: 20260513_is_core
Revises: 20260512_gs
Create Date: 2026-05-07
"""
import sqlalchemy as sa
from alembic import op


revision = "20260513_is_core"
down_revision = "20260512_gs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stocks",
        sa.Column(
            "is_core",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_stocks_is_core", "stocks", ["is_core"])


def downgrade() -> None:
    op.drop_index("ix_stocks_is_core", table_name="stocks")
    op.drop_column("stocks", "is_core")
