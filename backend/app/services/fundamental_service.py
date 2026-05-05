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
