"""v5 框架 — 目标价实时上行空间 API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.stock import Stock
from app.models.target_price_realtime import StockTargetPriceRealtime
from app.schemas.target_price_realtime import TargetPriceRealtimeRead
from app.services.target_price_service import (
    compute_realtime_for_all_watchlist,
    compute_realtime_for_stock,
)

router = APIRouter()


@router.get(
    "/stocks/{code}/target-price-realtime",
    response_model=TargetPriceRealtimeRead,
    tags=["target-price"],
)
async def get_target_price_realtime(
    code: str,
    recompute: bool = Query(False, description="True 强制重算"),
    db: AsyncSession = Depends(get_db),
):
    """获取单股实时目标价上行空间(主决策因子)"""
    res = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = res.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(404, f"股票 {code} 不存在")

    if recompute:
        await compute_realtime_for_stock(db, stock_id)

    res = await db.execute(
        select(StockTargetPriceRealtime).where(StockTargetPriceRealtime.stock_id == stock_id)
    )
    row = res.scalar_one_or_none()
    if not row:
        # 首次访问触发计算
        await compute_realtime_for_stock(db, stock_id)
        res = await db.execute(
            select(StockTargetPriceRealtime).where(StockTargetPriceRealtime.stock_id == stock_id)
        )
        row = res.scalar_one_or_none()

    if not row:
        raise HTTPException(404, "无法计算实时上行空间(无 K 线或研报数据)")

    return row


@router.post(
    "/target-price/recompute-all",
    tags=["target-price"],
)
async def recompute_all_watchlist(db: AsyncSession = Depends(get_db)):
    """重算所有自选股"""
    stats = await compute_realtime_for_all_watchlist(db)
    return stats


@router.get(
    "/target-price/ranking",
    response_model=list[TargetPriceRealtimeRead],
    tags=["target-price"],
)
async def get_target_price_ranking(
    limit: int = Query(50, ge=1, le=200),
    only_actionable: bool = Query(False, description="只返回有目标价 + 非 Veto"),
    db: AsyncSession = Depends(get_db),
):
    """全市场上行空间排名"""
    stmt = select(StockTargetPriceRealtime)
    if only_actionable:
        stmt = stmt.where(
            StockTargetPriceRealtime.final_score.isnot(None),
            StockTargetPriceRealtime.veto_triggered.is_(False),
        )
    stmt = stmt.order_by(StockTargetPriceRealtime.final_score.desc().nullslast()).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()
