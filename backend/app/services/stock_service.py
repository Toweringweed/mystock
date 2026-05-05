"""股票增删改查 + 自选股管理"""
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.schemas.stock import StockCreate

logger = logging.getLogger(__name__)


async def get_stock_by_code(db: AsyncSession, code: str) -> Stock | None:
    result = await db.execute(select(Stock).where(Stock.code == code))
    return result.scalar_one_or_none()


async def get_watchlist(db: AsyncSession) -> list[Stock]:
    result = await db.execute(
        select(Stock).where(Stock.is_watchlist == True).order_by(Stock.created_at)  # noqa: E712
    )
    return list(result.scalars().all())


async def get_all_watchlist_codes(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(Stock.code).where(Stock.is_watchlist == True)  # noqa: E712
    )
    return list(result.scalars().all())


async def get_all_watchlist_codes_with_info(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Stock.id, Stock.code, Stock.name, Stock.market).where(Stock.is_watchlist == True)  # noqa: E712
    )
    return [{"id": r.id, "code": r.code, "name": r.name, "market": r.market} for r in result.all()]


async def add_to_watchlist(db: AsyncSession, payload: StockCreate) -> Stock | None:
    """添加自选股：若已存在则更新标记，否则新建并触发数据回填"""
    existing = await get_stock_by_code(db, payload.code)

    if existing:
        if existing.is_watchlist:
            return existing
        existing.is_watchlist = True
        await db.flush()
        _trigger_backfill(existing.code, existing.market)
        return existing

    # 尝试从 AKShare 获取基础信息，失败时用 payload.name 兜底
    from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
    fetcher = AKShareFetcher()
    info = await fetcher.fetch_stock_info(payload.code, payload.market)
    if not info:
        logger.warning(f"[{payload.code}] 无法获取股票详细信息，使用兜底信息添加")
        info = {}

    stock = Stock(
        code=payload.code,
        market=payload.market,
        name=info.get("name") or payload.name or payload.code,
        industry=info.get("industry"),
        sector=info.get("sector"),
        is_watchlist=True,
        data_ready=False,
    )
    db.add(stock)
    await db.flush()

    # 触发异步数据回填（Celery）
    _trigger_backfill(stock.code, stock.market)
    logger.info(f"[{payload.code}] 已添加自选股，数据回填任务已提交")
    return stock


async def remove_from_watchlist(db: AsyncSession, code: str) -> None:
    """从自选股移除并删除该股票所有关联数据"""
    from sqlalchemy import delete
    from app.models.analysis import AnalysisReport, ChipDistribution, DivergenceSignal
    from app.models.fundamental import ProfitForecast, StockFundamental
    from app.models.news import IndustryNews, NewsStockRelation
    from app.models.stock_meta import StockNote
    from app.models.supply_chain import SupplyChain

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        return

    # 删除 news 关联（不删除 news 本体，可能被其他股票共享）
    await db.execute(delete(NewsStockRelation).where(NewsStockRelation.stock_id == stock_id))

    # 删除各类分析数据
    for model in [
        AnalysisReport, ChipDistribution, DivergenceSignal,
        StockFundamental, ProfitForecast, StockNote, SupplyChain,
    ]:
        await db.execute(delete(model).where(model.stock_id == stock_id))

    # 删除 K 线和技术指标
    from app.models.kline import StockDailyKline, StockTechnicalIndicator
    await db.execute(delete(StockDailyKline).where(StockDailyKline.stock_id == stock_id))
    await db.execute(delete(StockTechnicalIndicator).where(StockTechnicalIndicator.stock_id == stock_id))

    # 最后删除股票本体
    await db.execute(delete(Stock).where(Stock.id == stock_id))


async def mark_data_ready(db: AsyncSession, code: str) -> None:
    await db.execute(
        update(Stock).where(Stock.code == code).values(data_ready=True)
    )


def _trigger_backfill(code: str, market: str) -> None:
    """提交 Celery 任务，不阻塞当前请求"""
    try:
        from app.tasks.data_tasks import backfill_stock_data
        backfill_stock_data.delay(code, market)
    except Exception as e:
        logger.error(f"[{code}] 提交回填任务失败: {e}")
