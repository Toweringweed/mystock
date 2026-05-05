"""create tags and stock_tags tables

Revision ID: 20260502_tags
Revises: 20260502_conclusions
Create Date: 2026-05-02
"""
from alembic import op
import sqlalchemy as sa

revision = "20260502_tags"
down_revision = "20260502_conclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_tags_name"),
    )
    op.create_index("ix_tags_name", "tags", ["name"])
    op.create_index("ix_tags_category", "tags", ["category"])

    op.create_table(
        "stock_tags",
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "tag_id", sa.Integer(),
            sa.ForeignKey("tags.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("source", sa.String(8), nullable=False, server_default="manual"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("stock_id", "tag_id", name="pk_stock_tags"),
    )
    op.create_index("ix_stock_tags_stock_id", "stock_tags", ["stock_id"])
    op.create_index("ix_stock_tags_tag_id", "stock_tags", ["tag_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_tags_tag_id", table_name="stock_tags")
    op.drop_index("ix_stock_tags_stock_id", table_name="stock_tags")
    op.drop_table("stock_tags")
    op.drop_index("ix_tags_category", table_name="tags")
    op.drop_index("ix_tags_name", table_name="tags")
    op.drop_table("tags")
