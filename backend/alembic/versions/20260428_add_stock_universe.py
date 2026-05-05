"""add stock_universe table for local search cache

Revision ID: 20260428_stock_universe
Revises: 20260427_app_settings
Create Date: 2026-04-28
"""
from alembic import op
import sqlalchemy as sa

revision = "20260428_stock_universe"
down_revision = "20260427_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_universe",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("market", sa.String(2), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("industry", sa.String(50), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_stock_universe_name", "stock_universe", ["name"])
    op.create_index("ix_stock_universe_market", "stock_universe", ["market"])


def downgrade() -> None:
    op.drop_index("ix_stock_universe_name", table_name="stock_universe")
    op.drop_index("ix_stock_universe_market", table_name="stock_universe")
    op.drop_table("stock_universe")
