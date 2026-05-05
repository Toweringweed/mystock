"""K 线数据存取服务"""
import logging
from datetime import date, timedelta

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kline import StockDailyKline, StockTechnicalIndicator
from app.models.stock import Stock

logger = logging.getLogger(__name__)


async def _get_stock_id(db: AsyncSession, code: str) -> int | None:
    result = await db.execute(select(Stock.id).where(Stock.code == code))
    return result.scalar_one_or_none()


async def save_klines(db: AsyncSession, code: str, klines: list[dict]) -> int:
    """批量写入 K 线，ON CONFLICT DO NOTHING（幂等）"""
    if not klines:
        return 0

    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        logger.error(f"[{code}] 股票不存在，无法写入K线")
        return 0

    rows = [
        {
            "stock_id": stock_id,
            "trade_date": k["trade_date"],
            "open": k.get("open"),
            "high": k.get("high"),
            "low": k.get("low"),
            "close": k.get("close"),
            "volume": k.get("volume"),
            "amount": k.get("amount"),
            "turnover": k.get("turnover"),
            "change_pct": k.get("change_pct"),
        }
        for k in klines
    ]

    stmt = insert(StockDailyKline).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["stock_id", "trade_date"])
    result = await db.execute(stmt)
    await db.flush()

    saved = result.rowcount
    logger.info(f"[{code}] 写入 K 线 {saved}/{len(rows)} 条")
    return saved


async def get_daily_kline(
    db: AsyncSession, code: str, days: int = 90
) -> list[StockDailyKline]:
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return []

    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(StockDailyKline)
        .where(StockDailyKline.stock_id == stock_id, StockDailyKline.trade_date >= since)
        .order_by(StockDailyKline.trade_date)
    )
    return list(result.scalars().all())


async def get_kline_dataframe(db: AsyncSession, code: str, days: int = 300):
    """返回 pandas DataFrame，供技术分析引擎使用"""
    import pandas as pd

    klines = await get_daily_kline(db, code, days)
    if not klines:
        return pd.DataFrame()

    data = [
        {
            "trade_date": k.trade_date,
            "open": float(k.open or 0),
            "high": float(k.high or 0),
            "low": float(k.low or 0),
            "close": float(k.close or 0),
            "volume": int(k.volume or 0),
            "amount": float(k.amount or 0),
            "turnover": float(k.turnover or 0),
            "change_pct": float(k.change_pct or 0),
        }
        for k in klines
    ]
    df = pd.DataFrame(data)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    return df


async def save_indicators(db: AsyncSession, code: str, indicators: list[dict]) -> int:
    """批量写入技术指标，ON CONFLICT DO UPDATE"""
    if not indicators:
        return 0

    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return 0

    rows = [{"stock_id": stock_id, **ind} for ind in indicators]
    stmt = insert(StockTechnicalIndicator).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "trade_date"],
        set_={k: stmt.excluded[k] for k in rows[0] if k not in ("stock_id", "trade_date")},
    )
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount


async def get_indicators(
    db: AsyncSession, code: str, days: int = 90
) -> list[dict]:
    """返回技术指标列表，附带当日筹码快照数据"""
    from app.models.analysis import ChipDistribution
    from app.schemas.kline import IndicatorRead

    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return []

    since = date.today() - timedelta(days=days)

    # 技术指标
    ind_result = await db.execute(
        select(StockTechnicalIndicator)
        .where(
            StockTechnicalIndicator.stock_id == stock_id,
            StockTechnicalIndicator.trade_date >= since,
        )
        .order_by(StockTechnicalIndicator.trade_date)
    )
    indicators = list(ind_result.scalars().all())

    # 筹码快照（按日期索引）
    chip_result = await db.execute(
        select(ChipDistribution)
        .where(
            ChipDistribution.stock_id == stock_id,
            ChipDistribution.calc_date >= since,
        )
    )
    chip_by_date: dict[date, ChipDistribution] = {
        c.calc_date: c for c in chip_result.scalars().all()
    }

    rows = []
    for ind in indicators:
        chip = chip_by_date.get(ind.trade_date)
        row = IndicatorRead.model_validate(ind).model_dump()
        if chip:
            row["chip_profit_ratio"] = chip.profit_ratio
            row["chip_concentration"] = chip.concentration
            row["chip_avg_cost"] = float(chip.avg_cost) if chip.avg_cost else None
        rows.append(row)

    return rows


async def update_volume_ratios(db: AsyncSession, code: str) -> int:
    """计算并回填 stock_daily_kline.volume_ratio = volume / 5日均量

    用 window function 一次性填补缺失值，幂等（已计算过的不会重复更新）。
    """
    from sqlalchemy import text
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return 0
    result = await db.execute(
        text("""
            WITH avg5 AS (
              SELECT id, volume::float / NULLIF(
                AVG(volume) OVER (
                  PARTITION BY stock_id ORDER BY trade_date
                  ROWS BETWEEN 5 PRECEDING AND 1 PRECEDING
                ), 0
              ) AS ratio
              FROM stock_daily_kline WHERE stock_id = :sid
            )
            UPDATE stock_daily_kline k
            SET volume_ratio = a.ratio
            FROM avg5 a
            WHERE a.id = k.id
              AND k.volume_ratio IS NULL
              AND a.ratio IS NOT NULL
        """),
        {"sid": stock_id},
    )
    return result.rowcount
