"""extend quarterly_financials_history with D3/D7 fields (ROIC, FCF, accounts receivable days, goodwill, current/quick ratio, inventory days)

Revision ID: 20260508_qfinext
Revises: 20260507_backtest
Create Date: 2026-05-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260508_qfinext"
down_revision = "20260507_backtest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 为 D3 (护城河 5 子项)新增列
    op.add_column("quarterly_financials_history",
                  sa.Column("roic", sa.Numeric(8, 2), nullable=True))
    op.add_column("quarterly_financials_history",
                  sa.Column("fcf_yi", sa.Numeric(14, 2), nullable=True))  # 自由现金流(亿元)
    op.add_column("quarterly_financials_history",
                  sa.Column("fcf_to_revenue", sa.Numeric(8, 4), nullable=True))  # FCF/营收

    # 为 D7 (财务质量健康度)新增列
    op.add_column("quarterly_financials_history",
                  sa.Column("accounts_receivable_days", sa.Numeric(8, 2), nullable=True))
    op.add_column("quarterly_financials_history",
                  sa.Column("inventory_days", sa.Numeric(8, 2), nullable=True))
    op.add_column("quarterly_financials_history",
                  sa.Column("goodwill_yi", sa.Numeric(14, 2), nullable=True))  # 商誉(亿元)
    op.add_column("quarterly_financials_history",
                  sa.Column("goodwill_to_equity_ratio", sa.Numeric(8, 4), nullable=True))  # 商誉/净资产
    op.add_column("quarterly_financials_history",
                  sa.Column("current_ratio", sa.Numeric(8, 4), nullable=True))
    op.add_column("quarterly_financials_history",
                  sa.Column("quick_ratio", sa.Numeric(8, 4), nullable=True))


def downgrade() -> None:
    for col in [
        "roic", "fcf_yi", "fcf_to_revenue",
        "accounts_receivable_days", "inventory_days",
        "goodwill_yi", "goodwill_to_equity_ratio",
        "current_ratio", "quick_ratio",
    ]:
        op.drop_column("quarterly_financials_history", col)
