"""P1 indicators: capital_flows / lhb / insider_trades / calendar_events / industry_metrics
   + volume_ratio + ps + v_stock_peg view

Revision ID: 20260501_p1_indicators
Revises: 20260501_div_dedup
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260501_p1_indicators"
down_revision = "20260501_div_dedup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 现有表加列 ─────────────────────────────────────────
    op.add_column(
        "stock_daily_kline",
        sa.Column("volume_ratio", sa.Numeric(8, 4), nullable=True),
    )
    op.add_column(
        "stock_fundamentals",
        sa.Column("ps", sa.Numeric(10, 4), nullable=True),
    )

    # ── stock_capital_flows ────────────────────────────────
    op.create_table(
        "stock_capital_flows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("net_inflow", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_inflow_5d", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_inflow_20d", sa.Numeric(20, 2), nullable=True),
        sa.Column("shareholding_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("shareholding_volume", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint("stock_id", "trade_date", name="uq_capflow_stock_date"),
    )
    op.create_index("ix_capflow_stock_date", "stock_capital_flows", ["stock_id", "trade_date"])

    # ── stock_lhb ──────────────────────────────────────────
    op.create_table(
        "stock_lhb",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("buy_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("sell_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("change_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("top_buyers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("top_sellers", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint("stock_id", "trade_date", name="uq_lhb_stock_date"),
    )
    op.create_index("ix_stock_lhb_stock_id", "stock_lhb", ["stock_id"])
    op.create_index("ix_stock_lhb_trade_date", "stock_lhb", ["trade_date"])

    # ── insider_trades ─────────────────────────────────────
    insider_type = sa.Enum(
        "reduce", "increase",
        name="insider_trade_type_enum",
        create_type=True,
    )
    op.create_table(
        "insider_trades",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("ann_date", sa.Date(), nullable=False),
        sa.Column("trade_type", insider_type, nullable=False),
        sa.Column("holder_name", sa.String(200), nullable=False),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("pct_of_total", sa.Numeric(8, 4), nullable=True),
        sa.Column("pct_before", sa.Numeric(8, 4), nullable=True),
        sa.Column("pct_after", sa.Numeric(8, 4), nullable=True),
        sa.Column("price_low", sa.Numeric(12, 3), nullable=True),
        sa.Column("price_high", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "source_news_id", sa.Integer(),
            sa.ForeignKey("industry_news.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "ann_date", "trade_type", "holder_name",
            name="uq_insider_stock_date_type_holder",
        ),
    )
    op.create_index("ix_insider_stock_id", "insider_trades", ["stock_id"])
    op.create_index("ix_insider_ann_date", "insider_trades", ["ann_date"])

    # ── calendar_events ────────────────────────────────────
    cal_type = sa.Enum(
        "earnings_release", "restricted_release", "custom",
        "macro", "industry_conference",
        name="calendar_event_type_enum",
        create_type=True,
    )
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            nullable=True,  # 全市场事件可空
        ),
        sa.Column("event_type", cal_type, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "stock_id", "event_type", "event_date",
            name="uq_calendar_stock_type_date",
        ),
    )
    op.create_index("ix_calendar_stock_id", "calendar_events", ["stock_id"])
    op.create_index("ix_calendar_event_date", "calendar_events", ["event_date"])

    # ── industry_metrics ───────────────────────────────────
    op.create_table(
        "industry_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), nullable=True),
        sa.Column("unit", sa.String(40), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("extracted_from", sa.String(500), nullable=True),
        sa.Column("extracted_quote", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "metric_name", "period", "source",
            name="uq_industry_metric_period_source",
        ),
    )
    op.create_index("ix_industry_metric_name", "industry_metrics", ["metric_name"])

    # ── PEG view（forward_pe / profit_yoy 优先；TTM 为兜底） ─────
    op.execute("""
        CREATE OR REPLACE VIEW v_stock_peg AS
        SELECT
            f.stock_id,
            f.period,
            f.period_type,
            f.pe_ttm,
            f.profit_yoy,
            CASE WHEN f.profit_yoy IS NOT NULL AND f.profit_yoy > 0
                 THEN f.pe_ttm / f.profit_yoy END AS peg_ttm,
            (
                SELECT pf.forward_pe
                FROM profit_forecasts pf
                WHERE pf.stock_id = f.stock_id
                  AND pf.forecast_year = EXTRACT(YEAR FROM CURRENT_DATE)::int + 1
                ORDER BY pf.updated_at DESC LIMIT 1
            ) AS forward_pe_next,
            CASE
              WHEN f.profit_yoy IS NOT NULL AND f.profit_yoy > 0 THEN
                (SELECT pf.forward_pe FROM profit_forecasts pf
                 WHERE pf.stock_id = f.stock_id
                   AND pf.forecast_year = EXTRACT(YEAR FROM CURRENT_DATE)::int + 1
                 ORDER BY pf.updated_at DESC LIMIT 1) / f.profit_yoy
            END AS peg_forward
        FROM stock_fundamentals f
        WHERE f.period_type = 'ttm'
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_stock_peg")

    op.drop_index("ix_industry_metric_name", table_name="industry_metrics")
    op.drop_table("industry_metrics")

    op.drop_index("ix_calendar_event_date", table_name="calendar_events")
    op.drop_index("ix_calendar_stock_id", table_name="calendar_events")
    op.drop_table("calendar_events")
    sa.Enum(name="calendar_event_type_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_insider_ann_date", table_name="insider_trades")
    op.drop_index("ix_insider_stock_id", table_name="insider_trades")
    op.drop_table("insider_trades")
    sa.Enum(name="insider_trade_type_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_stock_lhb_trade_date", table_name="stock_lhb")
    op.drop_index("ix_stock_lhb_stock_id", table_name="stock_lhb")
    op.drop_table("stock_lhb")

    op.drop_index("ix_capflow_stock_date", table_name="stock_capital_flows")
    op.drop_table("stock_capital_flows")

    op.drop_column("stock_fundamentals", "ps")
    op.drop_column("stock_daily_kline", "volume_ratio")
