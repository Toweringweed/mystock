"""add stock_notes table

Revision ID: 20260420_stock_notes
Revises:
Create Date: 2026-04-20

"""
from alembic import op
import sqlalchemy as sa

revision = "20260420_stock_notes"
down_revision = "ac0531848f21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_notes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id"),
    )
    op.create_index("ix_stock_notes_stock_id", "stock_notes", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_notes_stock_id", table_name="stock_notes")
    op.drop_table("stock_notes")
