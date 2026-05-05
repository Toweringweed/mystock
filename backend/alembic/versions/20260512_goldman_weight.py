"""降低高盛/Goldman Sachs 权重 1.20 → 0.80

Revision ID: 20260512_gs
Revises: 20260511_text
Create Date: 2026-05-12

原因: 高盛对 AI 相关 A 股目标价显著高于其他投行(可能 25-40% 偏高),
直接计入加权目标价会带来系统性偏乐观风险,故下调权重。
"""
from alembic import op


revision = "20260512_gs"
down_revision = "20260511_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE institution_metadata
        SET weight_factor = 0.80,
            notes = COALESCE(notes, '') || ' [2026-05-12 下调:AI 板块目标价偏乐观]'
        WHERE name IN ('高盛', 'Goldman Sachs')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE institution_metadata
        SET weight_factor = 1.20,
            notes = '全球顶级投行,A股覆盖度高'
        WHERE name = '高盛';
        UPDATE institution_metadata
        SET weight_factor = 1.20,
            notes = '同高盛'
        WHERE name = 'Goldman Sachs';
    """)
