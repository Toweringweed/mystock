"""add personal_note column to stock_notes

Revision ID: 20260510_pnote
Revises: 20260509_tprt
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa


revision = "20260510_pnote"
down_revision = "20260509_tprt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_notes",
        sa.Column("personal_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stock_notes", "personal_note")
