"""supply chain intelligence tables

Revision ID: 20260606_supply_chain_intel
Revises: 20260515_stock_sync_status
Create Date: 2026-06-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260606_supply_chain_intel"
down_revision = "20260515_stock_sync_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supply_chain_companies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("stock_code", sa.String(length=10), nullable=True),
        sa.Column("market", sa.String(length=10), nullable=True),
        sa.Column("is_listed", sa.Boolean(), nullable=False),
        sa.Column("industry", sa.String(length=80), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("normalized_name", name="uq_supply_chain_company_normalized_name"),
    )
    op.create_index(
        "ix_supply_chain_companies_normalized_name",
        "supply_chain_companies",
        ["normalized_name"],
    )
    op.create_index(
        "ix_supply_chain_companies_stock_code",
        "supply_chain_companies",
        ["stock_code"],
    )

    op.create_table(
        "supply_chain_company_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("alias", sa.String(length=120), nullable=False),
        sa.Column("alias_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["supply_chain_companies.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("company_id", "alias", name="uq_supply_chain_company_alias"),
    )
    op.create_index(
        "ix_supply_chain_company_aliases_alias",
        "supply_chain_company_aliases",
        ["alias"],
    )
    op.create_index(
        "ix_supply_chain_company_aliases_company_id",
        "supply_chain_company_aliases",
        ["company_id"],
    )

    op.create_table(
        "supply_chain_relationships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("host_stock_id", sa.Integer(), nullable=False),
        sa.Column("source_company_id", sa.Integer(), nullable=False),
        sa.Column("target_company_id", sa.Integer(), nullable=False),
        sa.Column("legacy_supply_chain_id", sa.Integer(), nullable=True),
        sa.Column("relation_type", sa.String(length=30), nullable=False),
        sa.Column("product_desc", sa.Text(), nullable=True),
        sa.Column("cooperation_desc", sa.Text(), nullable=True),
        sa.Column("percentage", sa.Numeric(6, 2), nullable=True),
        sa.Column("importance", sa.String(length=10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("chain_layer", sa.String(length=20), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_source", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["host_stock_id"], ["stocks.id"]),
        sa.ForeignKeyConstraint(["source_company_id"], ["supply_chain_companies.id"]),
        sa.ForeignKeyConstraint(["target_company_id"], ["supply_chain_companies.id"]),
        sa.ForeignKeyConstraint(["legacy_supply_chain_id"], ["supply_chains.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "host_stock_id",
            "source_company_id",
            "target_company_id",
            "relation_type",
            "product_desc",
            name="uq_supply_chain_relationship",
        ),
    )
    op.create_index(
        "ix_supply_chain_relationships_host_stock_id",
        "supply_chain_relationships",
        ["host_stock_id"],
    )
    op.create_index(
        "ix_supply_chain_relationships_source_company_id",
        "supply_chain_relationships",
        ["source_company_id"],
    )
    op.create_index(
        "ix_supply_chain_relationships_target_company_id",
        "supply_chain_relationships",
        ["target_company_id"],
    )
    op.create_index(
        "ix_supply_chain_relationships_legacy_supply_chain_id",
        "supply_chain_relationships",
        ["legacy_supply_chain_id"],
    )
    op.create_index(
        "ix_supply_chain_relationships_relation_type",
        "supply_chain_relationships",
        ["relation_type"],
    )

    op.create_table(
        "supply_chain_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("relationship_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("source_title", sa.String(length=300), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["relationship_id"], ["supply_chain_relationships.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_supply_chain_evidence_relationship_id",
        "supply_chain_evidence",
        ["relationship_id"],
    )

    op.create_table(
        "supply_chain_news_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("news_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("relationship_id", sa.Integer(), nullable=True),
        sa.Column("supply_chain_id", sa.Integer(), nullable=True),
        sa.Column("matched_alias", sa.String(length=120), nullable=False),
        sa.Column("relevance", sa.Float(), nullable=False),
        sa.Column("impact_direction", sa.String(length=10), nullable=True),
        sa.Column("impact_summary", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["news_id"], ["industry_news.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["supply_chain_companies.id"]),
        sa.ForeignKeyConstraint(["relationship_id"], ["supply_chain_relationships.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supply_chain_id"], ["supply_chains.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("news_id", "stock_id", "company_id", name="uq_supply_chain_news_link"),
    )
    op.create_index("ix_supply_chain_news_links_news_id", "supply_chain_news_links", ["news_id"])
    op.create_index("ix_supply_chain_news_links_stock_id", "supply_chain_news_links", ["stock_id"])
    op.create_index("ix_supply_chain_news_links_company_id", "supply_chain_news_links", ["company_id"])
    op.create_index(
        "ix_supply_chain_news_links_relationship_id",
        "supply_chain_news_links",
        ["relationship_id"],
    )
    op.create_index(
        "ix_supply_chain_news_links_supply_chain_id",
        "supply_chain_news_links",
        ["supply_chain_id"],
    )

    op.create_table(
        "supply_chain_event_impacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("news_link_id", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("stock_return_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("benchmark_return_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("excess_return_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["news_link_id"], ["supply_chain_news_links.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("news_link_id", "horizon_days", name="uq_supply_chain_event_impact"),
    )
    op.create_index(
        "ix_supply_chain_event_impacts_news_link_id",
        "supply_chain_event_impacts",
        ["news_link_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_supply_chain_event_impacts_news_link_id", table_name="supply_chain_event_impacts")
    op.drop_table("supply_chain_event_impacts")
    op.drop_index("ix_supply_chain_news_links_supply_chain_id", table_name="supply_chain_news_links")
    op.drop_index("ix_supply_chain_news_links_relationship_id", table_name="supply_chain_news_links")
    op.drop_index("ix_supply_chain_news_links_company_id", table_name="supply_chain_news_links")
    op.drop_index("ix_supply_chain_news_links_stock_id", table_name="supply_chain_news_links")
    op.drop_index("ix_supply_chain_news_links_news_id", table_name="supply_chain_news_links")
    op.drop_table("supply_chain_news_links")
    op.drop_index("ix_supply_chain_evidence_relationship_id", table_name="supply_chain_evidence")
    op.drop_table("supply_chain_evidence")
    op.drop_index("ix_supply_chain_relationships_relation_type", table_name="supply_chain_relationships")
    op.drop_index("ix_supply_chain_relationships_legacy_supply_chain_id", table_name="supply_chain_relationships")
    op.drop_index("ix_supply_chain_relationships_target_company_id", table_name="supply_chain_relationships")
    op.drop_index("ix_supply_chain_relationships_source_company_id", table_name="supply_chain_relationships")
    op.drop_index("ix_supply_chain_relationships_host_stock_id", table_name="supply_chain_relationships")
    op.drop_table("supply_chain_relationships")
    op.drop_index("ix_supply_chain_company_aliases_company_id", table_name="supply_chain_company_aliases")
    op.drop_index("ix_supply_chain_company_aliases_alias", table_name="supply_chain_company_aliases")
    op.drop_table("supply_chain_company_aliases")
    op.drop_index("ix_supply_chain_companies_stock_code", table_name="supply_chain_companies")
    op.drop_index("ix_supply_chain_companies_normalized_name", table_name="supply_chain_companies")
    op.drop_table("supply_chain_companies")
