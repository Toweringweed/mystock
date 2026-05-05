"""add 3 conclusion columns to analysis_reports

Revision ID: 20260502_conclusions
Revises: 20260501_segments
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260502_conclusions"
down_revision = "20260501_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analysis_reports",
        sa.Column("industry_inflection", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("external_disruption", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "analysis_reports",
        sa.Column("action_suggestion", sa.String(length=240), nullable=True),
    )
    # 一次性回填 action_suggestion：从已有 full_report.suggestion 取值
    op.execute(
        """
        UPDATE analysis_reports
        SET action_suggestion = LEFT(full_report->>'suggestion', 240)
        WHERE full_report ? 'suggestion'
          AND full_report->>'suggestion' IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("analysis_reports", "action_suggestion")
    op.drop_column("analysis_reports", "external_disruption")
    op.drop_column("analysis_reports", "industry_inflection")
