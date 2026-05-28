from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.stock import StockCoreUpdate, StockCreate, StockRead, StockSearch
from app.schemas.analysis import WatchlistTableRow

router = APIRouter()


@router.get("/watchlist/table", response_model=list[WatchlistTableRow])
async def get_watchlist_table(db: AsyncSession = Depends(get_db)):
    """获取自选股表格数据（含基本面、预测、行情）"""
    from app.services.table_service import get_watchlist_table as _get
    return await _get(db)


@router.get("/search", response_model=list[StockSearch])
async def search_stocks(
    q: str = Query(..., min_length=1, description="股票代码或名称关键词"),
    db: AsyncSession = Depends(get_db),
):
    """搜索 A股/港股（查本地缓存，毫秒级响应）"""
    from app.services.stock_universe_service import search_universe, get_universe_count
    from app.services.data_fetcher.akshare_fetcher import search_stocks as _search_online

    # 若本地库还没数据（首次启动尚未同步完成），降级到在线搜索
    count = await get_universe_count(db)
    if count == 0:
        return await _search_online(q)

    return await search_universe(db, q)


@router.get("/watchlist", response_model=list[StockRead])
async def get_watchlist(db: AsyncSession = Depends(get_db)):
    """获取自选股列表"""
    from app.services.stock_service import get_watchlist as _get
    return await _get(db)


@router.post("/watchlist", response_model=StockRead, status_code=201)
async def add_to_watchlist(
    payload: StockCreate,
    db: AsyncSession = Depends(get_db),
):
    """添加自选股，触发数据回填任务"""
    from app.services.stock_service import (
        add_to_watchlist as _add,
        mark_sync_failed,
        mark_sync_pending,
        trigger_backfill,
    )
    stock = await _add(db, payload)
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在或不支持")
    code = stock.code
    market = stock.market
    needs_backfill = not stock.data_ready
    await db.commit()
    await db.refresh(stock)
    if needs_backfill:
        try:
            task_id = trigger_backfill(code, market)
            await mark_sync_pending(db, code, task_id)
            await db.commit()
            await db.refresh(stock)
        except Exception as e:
            await mark_sync_failed(db, code, f"提交回填任务失败: {e}")
            await db.commit()
            raise HTTPException(
                status_code=503,
                detail="自选股已添加，但数据回填任务提交失败，请稍后在设置页手动刷新",
            ) from e
    return stock


@router.delete("/watchlist/{code}", status_code=204)
async def remove_from_watchlist(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """从自选股移除（历史数据保留）"""
    from app.services.stock_service import remove_from_watchlist as _remove
    await _remove(db, code)


@router.patch("/watchlist/{code}/core", response_model=StockRead)
async def set_core_flag(
    code: str,
    payload: StockCoreUpdate,
    db: AsyncSession = Depends(get_db),
):
    """标记/取消核心自选股"""
    from app.services.stock_service import set_core_flag as _set
    stock = await _set(db, code, payload.is_core)
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在或不在自选股中")
    return stock


@router.get("/{code}", response_model=StockRead)
async def get_stock(code: str, db: AsyncSession = Depends(get_db)):
    """获取单只股票基础信息"""
    from app.services.stock_service import get_stock_by_code as _get
    stock = await _get(db, code)
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")
    return stock
