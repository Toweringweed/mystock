"""create backtest infrastructure tables (5 tables)

Revision ID: 20260507_backtest
Revises: 20260506_revisions
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260507_backtest"
down_revision = "20260506_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────
    # 1. stock_daily_factors — 每日估值因子(扩充 stock_daily_kline 不能装下)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "stock_daily_factors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close_price", sa.Numeric(12, 3)),
        sa.Column("change_pct", sa.Numeric(8, 4)),
        sa.Column("pe_ttm", sa.Numeric(10, 2)),
        sa.Column("pe_static", sa.Numeric(10, 2)),
        sa.Column("pb", sa.Numeric(10, 2)),
        sa.Column("ps", sa.Numeric(10, 2)),
        sa.Column("peg", sa.Numeric(10, 4)),
        sa.Column("market_cap_total", sa.Numeric(16, 2)),         # 总市值(亿元)
        sa.Column("market_cap_circulating", sa.Numeric(16, 2)),  # 流通市值
        # 来源:akshare stock_value_em
        sa.Column("source", sa.String(32), server_default="akshare_em"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("stock_id", "trade_date",
                            name="uq_stock_daily_factors_stock_date"),
    )
    op.create_index("ix_stock_daily_factors_stock_date",
                    "stock_daily_factors",
                    ["stock_id", sa.text("trade_date DESC")])

    # ──────────────────────────────────────────────────────────
    # 2. industry_daily_index — 行业指数(申万通信/半导体/新能源)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "industry_daily_index",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("index_code", sa.String(16), nullable=False),  # 801770 / 801080 / 801950
        sa.Column("index_name", sa.String(64), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Numeric(14, 4)),
        sa.Column("change_pct", sa.Numeric(8, 4)),
        sa.Column("volume", sa.Numeric(20, 2)),
        sa.Column("pe_median", sa.Numeric(10, 2)),     # 行业 PE 中位数(若可得)
        sa.Column("source", sa.String(32), server_default="akshare"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("index_code", "trade_date",
                            name="uq_industry_index_code_date"),
    )
    op.create_index("ix_industry_index_code_date",
                    "industry_daily_index",
                    ["index_code", sa.text("trade_date DESC")])

    # ──────────────────────────────────────────────────────────
    # 3. quarterly_financials_history — 历史季度财报(完整版,与 stock_fundamentals 互补)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "quarterly_financials_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),  # 财报期末(2024-03-31)
        sa.Column("period_label", sa.String(8), nullable=False),  # 2024Q1
        sa.Column("revenue_yi", sa.Numeric(14, 2)),
        sa.Column("net_profit_yi", sa.Numeric(14, 2)),
        sa.Column("net_profit_deducted_yi", sa.Numeric(14, 2)),  # 扣非
        sa.Column("eps", sa.Numeric(10, 4)),
        sa.Column("roe", sa.Numeric(8, 2)),
        sa.Column("roe_weighted", sa.Numeric(8, 2)),  # 加权 ROE
        sa.Column("gross_margin", sa.Numeric(8, 2)),
        sa.Column("net_margin", sa.Numeric(8, 2)),
        sa.Column("debt_ratio", sa.Numeric(8, 2)),
        sa.Column("cash_flow_to_profit", sa.Numeric(8, 4)),  # 经营现金流/净利
        sa.Column("revenue_yoy", sa.Numeric(8, 2)),
        sa.Column("profit_yoy", sa.Numeric(8, 2)),
        sa.Column("profit_qoq", sa.Numeric(8, 2)),
        sa.Column("source", sa.String(32), server_default="akshare_em"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("stock_id", "period_end",
                            name="uq_qfin_stock_period"),
    )
    op.create_index("ix_qfin_stock_period",
                    "quarterly_financials_history",
                    ["stock_id", sa.text("period_end DESC")])

    # ──────────────────────────────────────────────────────────
    # 4. institution_metadata — 机构元数据(支持机构权重细化建模)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "institution_metadata",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("name_en", sa.String(64)),
        # 类型
        sa.Column("type", sa.String(16), nullable=False),  # foreign / domestic_top / domestic_mid / domestic_small
        sa.Column("is_foreign", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        # 静态权重(初始基于经验,后续动态调整)
        sa.Column("weight_factor", sa.Numeric(4, 2), server_default="1.00"),
        # 动态历史预测准确度(基于 actual vs forecast 偏差;由后续任务计算)
        sa.Column("track_record_alpha", sa.Numeric(8, 4)),  # 平均超额收益预测能力
        sa.Column("track_record_n_samples", sa.Integer(), server_default="0"),
        sa.Column("last_calibrated_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"),
                  onupdate=sa.text("now()"), nullable=False),
    )

    # ──────────────────────────────────────────────────────────
    # 5. backtest_snapshots — 回测样本永久存(下次不用重算)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        "backtest_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("anchor_date", sa.Date(), nullable=False),
        # 8 维度评分
        sa.Column("d1_industry", sa.Numeric(4, 1)),
        sa.Column("d2_disruption", sa.Numeric(4, 1)),
        sa.Column("d3_moat", sa.Numeric(4, 1)),
        sa.Column("d4_valuation", sa.Numeric(4, 1)),
        sa.Column("d5_performance", sa.Numeric(4, 1)),
        sa.Column("d6_narrative", sa.Numeric(4, 1)),
        sa.Column("d7_financial", sa.Numeric(4, 1)),
        sa.Column("d8_governance", sa.Numeric(4, 1)),
        sa.Column("d9_momentum", sa.Numeric(4, 1)),  # 新增因子(建模用)
        sa.Column("overall_8d", sa.Numeric(4, 2)),
        sa.Column("veto_triggered", sa.Boolean(), server_default=sa.text("false")),

        # 当时点的关键原始数据(避免重算)
        sa.Column("price_at_anchor", sa.Numeric(12, 3)),
        sa.Column("pe_ttm", sa.Numeric(10, 2)),
        sa.Column("fwd_pe_2026", sa.Numeric(10, 2)),
        sa.Column("profit_yoy", sa.Numeric(8, 2)),
        sa.Column("research_count_90d", sa.Integer()),
        sa.Column("upgrade_count_90d", sa.Integer()),
        sa.Column("avg_target_price", sa.Numeric(10, 2)),

        # 后续 horizon 实际涨幅(可空,等到 horizon 到位后由 task 补)
        sa.Column("return_30d", sa.Numeric(8, 2)),
        sa.Column("return_60d", sa.Numeric(8, 2)),
        sa.Column("return_90d", sa.Numeric(8, 2)),
        sa.Column("return_120d", sa.Numeric(8, 2)),

        # 完整子项(JSONB,灵活存储所有可能的细化因子)
        sa.Column("subscore_details", JSONB()),

        sa.Column("framework_version", sa.String(16), server_default="8d_v2"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("stock_id", "anchor_date", "framework_version",
                            name="uq_backtest_snap_stock_anchor"),
    )
    op.create_index("ix_backtest_snap_anchor", "backtest_snapshots",
                    [sa.text("anchor_date DESC")])
    op.create_index("ix_backtest_snap_stock_anchor", "backtest_snapshots",
                    ["stock_id", sa.text("anchor_date DESC")])

    # 初始化机构元数据(种子数据)
    op.execute("""
        INSERT INTO institution_metadata (name, type, is_foreign, weight_factor, notes) VALUES
            -- 注:高盛权重已在 20260512_gs 迁移中下调至 0.80(原因:AI 板块目标价系统性偏乐观)
            ('高盛', 'foreign', true, 1.20, '全球顶级投行,A股覆盖度高'),
            ('Goldman Sachs', 'foreign', true, 1.20, '同高盛'),
            ('摩根士丹利', 'foreign', true, 1.20, '全球顶级投行'),
            ('Morgan Stanley', 'foreign', true, 1.20, '同摩根士丹利'),
            ('摩根大通', 'foreign', true, 1.20, '全球顶级投行'),
            ('JPMorgan', 'foreign', true, 1.20, '同摩根大通'),
            ('美银证券', 'foreign', true, 1.20, '全球顶级投行'),
            ('美银美林', 'foreign', true, 1.20, '同美银证券'),
            ('瑞银 UBS', 'foreign', true, 1.20, '欧洲顶级投行'),
            ('瑞银', 'foreign', true, 1.20, '同瑞银 UBS'),
            ('UBS', 'foreign', true, 1.20, '同瑞银 UBS'),
            ('花旗', 'foreign', true, 1.20, '美国顶级投行'),
            ('Citigroup', 'foreign', true, 1.20, '同花旗'),
            ('巴克莱', 'foreign', true, 1.20, '欧洲投行'),
            ('Barclays', 'foreign', true, 1.20, '同巴克莱'),
            ('汇丰', 'foreign', true, 1.20, '英资银行'),
            ('HSBC', 'foreign', true, 1.20, '同汇丰'),
            ('野村', 'foreign', true, 1.10, '日资,A股覆盖中等'),
            ('Nomura', 'foreign', true, 1.10, '同野村'),
            ('大和', 'foreign', true, 1.10, '日资'),
            ('Daiwa', 'foreign', true, 1.10, '同大和'),
            ('麦格理', 'foreign', true, 1.10, '澳资'),
            ('Macquarie', 'foreign', true, 1.10, '同麦格理'),
            ('里昂证券', 'foreign', true, 1.15, '法国券商,A股覆盖较好'),
            ('CLSA', 'foreign', true, 1.15, '同里昂'),
            ('海通国际', 'foreign', true, 1.10, '中资海外子'),
            ('中金公司', 'domestic_top', false, 1.00, '中资头部'),
            ('中金', 'domestic_top', false, 1.00, '中资头部'),
            ('CICC', 'domestic_top', false, 1.00, '同中金'),
            ('中信证券', 'domestic_top', false, 1.00, '中资头部'),
            ('华泰证券', 'domestic_top', false, 1.00, '中资头部'),
            ('国泰海通', 'domestic_top', false, 1.00, '中资头部'),
            ('国泰君安', 'domestic_top', false, 1.00, '中资头部'),
            ('海通证券', 'domestic_top', false, 1.00, '中资头部'),
            ('招商证券', 'domestic_top', false, 1.00, '中资头部'),
            ('国信证券', 'domestic_top', false, 1.00, '中资头部'),
            ('东方证券', 'domestic_top', false, 1.00, '中资头部'),
            ('东吴证券', 'domestic_mid', false, 0.95, '中资中型'),
            ('国投证券', 'domestic_mid', false, 0.95, '中资中型'),
            ('华安证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('华金证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('天风证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('开源证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('太平洋证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('华龙证券', 'domestic_small', false, 0.80, '中资小型'),
            ('华西证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('民生证券', 'domestic_mid', false, 0.90, '中资中型'),
            ('国海证券', 'domestic_small', false, 0.80, '中资小型'),
            ('信达证券', 'domestic_small', false, 0.80, '中资小型');
    """)


def downgrade() -> None:
    op.drop_index("ix_backtest_snap_stock_anchor", table_name="backtest_snapshots")
    op.drop_index("ix_backtest_snap_anchor", table_name="backtest_snapshots")
    op.drop_table("backtest_snapshots")
    op.drop_table("institution_metadata")
    op.drop_index("ix_qfin_stock_period", table_name="quarterly_financials_history")
    op.drop_table("quarterly_financials_history")
    op.drop_index("ix_industry_index_code_date", table_name="industry_daily_index")
    op.drop_table("industry_daily_index")
    op.drop_index("ix_stock_daily_factors_stock_date", table_name="stock_daily_factors")
    op.drop_table("stock_daily_factors")
