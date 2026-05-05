"""dedupe divergence_signals + add unique constraint

Revision ID: 20260501_div_dedup
Revises: 20260501_events
Create Date: 2026-05-01
"""
from alembic import op

revision = "20260501_div_dedup"
down_revision = "20260501_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 删除重复行（保留每组最大 id），再加唯一约束
    op.execute("""
        DELETE FROM divergence_signals a
        USING divergence_signals b
        WHERE a.stock_id = b.stock_id
          AND a.signal_type = b.signal_type
          AND a.detected_date = b.detected_date
          AND a.id < b.id
    """)
    op.create_unique_constraint(
        "uq_divergence_stock_type_date",
        "divergence_signals",
        ["stock_id", "signal_type", "detected_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_divergence_stock_type_date",
        "divergence_signals",
        type_="unique",
    )
