"""基本面数据存取服务"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fundamental import ProfitForecast, StockFundamental
from app.models.stock import Stock
from app.schemas.analysis import ForecastItem, FundamentalRead

logger = logging.getLogger(__name__)


async def _get_stock_id(db: AsyncSession, code: str) -> int | None:
    result = await db.execute(select(Stock.id, Stock.name).where(Stock.code == code))
    row = result.first()
    return (row.id, row.name) if row else (None, None)


async def save_fundamental(db: AsyncSession, code: str, data: dict) -> None:
    """写入最新基本面快照（TTM 类型）"""
    stock_id, _ = await _get_stock_id(db, code)
    if not stock_id:
        return

    period = datetime.now().strftime("%Y-TTM")
    values = {
        "stock_id": stock_id,
        "period": period,
        "period_type": "ttm",
        "pe_ttm": data.get("pe_ttm"),
        "pb": data.get("pb"),
        "roe": data.get("roe"),
        "gross_margin": data.get("gross_margin"),
        "net_margin": data.get("net_margin"),
        "debt_ratio": data.get("debt_ratio"),
        "revenue": data.get("revenue"),
        "net_profit": data.get("net_profit"),
        "eps": data.get("eps"),
        "revenue_yoy": data.get("revenue_yoy"),
        "profit_yoy": data.get("profit_yoy"),
    }
    stmt = insert(StockFundamental).values(**values)
    update_fields = {k: stmt.excluded[k] for k in values if k not in ("stock_id", "period", "period_type")}
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "period", "period_type"],
        set_=update_fields,
    )
    await db.execute(stmt)
    await db.flush()


async def save_quarterly_fundamentals(
    db: AsyncSession, code: str, periods: list[dict]
) -> int:
    """写多个季度报告期数据,双写:
       - stock_fundamentals (period_type=quarterly) — 用于一致预期/财报追踪 join
       - quarterly_financials_history — 用于"护城河变动追踪"季度走势

       返回写入的报告期数。periods 是 fetch_quarterly_fundamentals 返回的列表。
    """
    if not periods:
        return 0
    stock_id, _ = await _get_stock_id(db, code)
    if not stock_id:
        return 0

    from app.models.backtest_infra import QuarterlyFinancialsHistory

    def _yi_to_yuan(value):
        return float(value) * 1e8 if value is not None else None

    def _numeric_8_4(value):
        if value is None:
            return None
        value = float(value)
        return value if abs(value) < 10000 else None

    written = 0
    for p in periods:
        period_label = p["period_label"]
        period_end = p["period_end"]

        # 1) stock_fundamentals (quarterly) — 注:此表无 quick_ratio,只在 quarterly_financials_history 写
        stmt = insert(StockFundamental).values(
            stock_id=stock_id,
            period=period_label,
            period_type="quarterly",
            revenue=_yi_to_yuan(p.get("revenue_yi")),
            net_profit=_yi_to_yuan(p.get("net_profit_yi")),
            eps=p.get("eps"),
            roe=p.get("roe"),
            gross_margin=p.get("gross_margin"),
            net_margin=p.get("net_margin"),
            debt_ratio=p.get("debt_ratio"),
            cash_flow_ratio=_numeric_8_4(p.get("cash_flow_to_profit")),
            revenue_yoy=_numeric_8_4(p.get("revenue_yoy")),
            profit_yoy=_numeric_8_4(p.get("profit_yoy")),
            current_ratio=_numeric_8_4(p.get("current_ratio")),
        )
        update_cols = {
            k: stmt.excluded[k]
            for k in [
                "revenue", "net_profit", "eps", "roe", "gross_margin", "net_margin",
                "debt_ratio", "cash_flow_ratio", "revenue_yoy", "profit_yoy",
                "current_ratio",
            ]
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=["stock_id", "period", "period_type"],
            set_=update_cols,
        )
        await db.execute(stmt)

        # 2) quarterly_financials_history
        qstmt = insert(QuarterlyFinancialsHistory).values(
            stock_id=stock_id,
            period_end=period_end,
            period_label=period_label,
            revenue_yi=p.get("revenue_yi"),
            net_profit_yi=p.get("net_profit_yi"),
            net_profit_deducted_yi=p.get("net_profit_deducted_yi"),
            eps=p.get("eps"),
            roe=p.get("roe"),
            roe_weighted=p.get("roe_weighted"),
            gross_margin=p.get("gross_margin"),
            net_margin=p.get("net_margin"),
            debt_ratio=p.get("debt_ratio"),
            cash_flow_to_profit=p.get("cash_flow_to_profit"),
            revenue_yoy=p.get("revenue_yoy"),
            profit_yoy=p.get("profit_yoy"),
            profit_qoq=p.get("profit_qoq"),
            roic=p.get("roic"),
            fcf_yi=p.get("fcf_yi"),
            current_ratio=p.get("current_ratio"),
            quick_ratio=p.get("quick_ratio"),
            source="akshare_indicator",
        )
        qupdate = {
            k: qstmt.excluded[k]
            for k in [
                "revenue_yi", "net_profit_yi", "net_profit_deducted_yi", "eps",
                "roe", "roe_weighted", "gross_margin", "net_margin", "debt_ratio",
                "cash_flow_to_profit", "revenue_yoy", "profit_yoy", "profit_qoq",
                "roic", "fcf_yi", "current_ratio", "quick_ratio",
            ]
        }
        qstmt = qstmt.on_conflict_do_update(
            index_elements=["stock_id", "period_end"],
            set_=qupdate,
        )
        await db.execute(qstmt)
        written += 1

    await db.flush()
    return written


async def get_fundamental(db: AsyncSession, code: str) -> FundamentalRead:
    stock_id, name = await _get_stock_id(db, code)
    if not stock_id:
        return FundamentalRead(code=code, name=code)

    # 最新 TTM 基本面
    result = await db.execute(
        select(StockFundamental)
        .where(StockFundamental.stock_id == stock_id, StockFundamental.period_type == "ttm")
        .order_by(StockFundamental.updated_at.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()

    # 盈利预测
    forecast_result = await db.execute(
        select(ProfitForecast)
        .where(ProfitForecast.stock_id == stock_id)
        .order_by(ProfitForecast.forecast_year)
    )
    forecasts = list(forecast_result.scalars().all())

    def _f(col):
        v = getattr(latest, col, None) if latest else None
        return float(v) if v is not None else None

    pe_ttm = _f("pe_ttm")
    net_profit_raw = _f("net_profit")  # 元
    net_profit_ttm = round(net_profit_raw / 1e8, 2) if net_profit_raw else None

    # 市值 = PE-TTM × 净利润TTM（亿元）
    market_cap = None
    if pe_ttm and net_profit_raw:
        market_cap = round(pe_ttm * net_profit_raw / 1e8, 1)

    return FundamentalRead(
        code=code,
        name=name or code,
        pe_ttm=pe_ttm,
        pb=_f("pb"),
        roe=_f("roe"),
        gross_margin=_f("gross_margin"),
        net_margin=_f("net_margin"),
        debt_ratio=_f("debt_ratio"),
        current_ratio=_f("current_ratio"),
        cash_flow_ratio=_f("cash_flow_ratio"),
        revenue_yoy=_f("revenue_yoy"),
        profit_yoy=_f("profit_yoy"),
        net_profit_ttm=net_profit_ttm,
        market_cap=market_cap,
        forecasts=[ForecastItem.model_validate(f) for f in forecasts],
    )
