"""add app_settings table

Revision ID: 20260427_app_settings
Revises: 20260420_stock_notes
Create Date: 2026-04-27
"""
from alembic import op
import sqlalchemy as sa

revision = "20260427_app_settings"
down_revision = "20260420_stock_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("is_secret", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
