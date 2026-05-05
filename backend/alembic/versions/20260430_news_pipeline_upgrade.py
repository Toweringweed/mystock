"""news pipeline upgrade: scoring fields, stock_aliases, simhash dedup

Revision ID: 20260430_news_pipeline
Revises: 20260428_stock_universe
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa

revision = "20260430_news_pipeline"
down_revision = "20260428_stock_universe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── industry_news: 新增打分流水线字段 ─────────────────────────
    with op.batch_alter_table("industry_news") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("source_authority", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("simhash", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("direction", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("urgency", sa.String(10), nullable=True))
        batch_op.add_column(sa.Column("rule_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("llm_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("importance_score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.create_index("ix_industry_news_simhash", "industry_news", ["simhash"])
    op.create_index("ix_industry_news_urgency", "industry_news", ["urgency"])
    op.create_index(
        "ix_industry_news_importance_score", "industry_news", ["importance_score"]
    )
    op.create_index("ix_industry_news_processed_at", "industry_news", ["processed_at"])

    # ── stock_aliases: 新表 ────────────────────────────────────────
    op.create_table(
        "stock_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id",
            sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(100), nullable=False),
        sa.Column("alias_type", sa.String(20), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("stock_id", "alias", name="uq_stock_aliases_stock_alias"),
    )
    op.create_index("ix_stock_aliases_stock_id", "stock_aliases", ["stock_id"])
    op.create_index("ix_stock_aliases_alias", "stock_aliases", ["alias"])


def downgrade() -> None:
    op.drop_index("ix_stock_aliases_alias", table_name="stock_aliases")
    op.drop_index("ix_stock_aliases_stock_id", table_name="stock_aliases")
    op.drop_table("stock_aliases")

    op.drop_index("ix_industry_news_processed_at", table_name="industry_news")
    op.drop_index("ix_industry_news_importance_score", table_name="industry_news")
    op.drop_index("ix_industry_news_urgency", table_name="industry_news")
    op.drop_index("ix_industry_news_simhash", table_name="industry_news")

    with op.batch_alter_table("industry_news") as batch_op:
        batch_op.drop_column("processed_at")
        batch_op.drop_column("importance_score")
        batch_op.drop_column("llm_score")
        batch_op.drop_column("rule_score")
        batch_op.drop_column("urgency")
        batch_op.drop_column("direction")
        batch_op.drop_column("simhash")
        batch_op.drop_column("source_authority")
        batch_op.drop_column("category")
