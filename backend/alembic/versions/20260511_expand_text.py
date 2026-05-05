"""expand analysis_reports text columns for richer conclusion/action_suggestion

Revision ID: 20260511_text
Revises: 20260510_pnote
Create Date: 2026-05-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260511_text"
down_revision = "20260510_pnote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 扩容 conclusion (200) 和 action_suggestion (240) 为 TEXT,以容纳 6D 框架的 100-300 字 富文本
    op.alter_column("analysis_reports", "conclusion",
                    existing_type=sa.String(200),
                    type_=sa.Text(),
                    existing_nullable=True)
    op.alter_column("analysis_reports", "action_suggestion",
                    existing_type=sa.String(240),
                    type_=sa.Text(),
                    existing_nullable=True)


def downgrade() -> None:
    op.alter_column("analysis_reports", "action_suggestion",
                    existing_type=sa.Text(),
                    type_=sa.String(240),
                    existing_nullable=True)
    op.alter_column("analysis_reports", "conclusion",
                    existing_type=sa.Text(),
                    type_=sa.String(200),
                    existing_nullable=True)
