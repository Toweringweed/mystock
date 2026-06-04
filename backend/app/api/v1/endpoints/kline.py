from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.kline import IndicatorRead, KlineRead

router = APIRouter()


@router.get("/{code}/daily", response_model=list[KlineRead])
async def get_daily_kline(
    code: str,
    days: int = Query(90, ge=30, le=1000, description="获取最近N个交易日"),
    db: AsyncSession = Depends(get_db),
):
    """获取日线 K 线数据"""
    from app.services.kline_service import get_daily_kline as _get
    return await _get(db, code, days)


@router.get("/{code}/indicators", response_model=list[IndicatorRead])
async def get_indicators(
    code: str,
    days: int = Query(90, ge=30, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """获取技术指标数据"""
    from app.services.kline_service import get_indicators as _get
    return await _get(db, code, days)


@router.post("/{code}/recalc", status_code=202)
async def recalc_indicators(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """手动触发：补齐最新 K 线 + 重算技术指标（用于数据缺失时修复）"""
    from sqlalchemy import select

    from app.models.stock import Stock

    result = await db.execute(select(Stock).where(Stock.code == code))
    stock = result.scalar_one_or_none()
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    try:
        # 1. 补齐最近 K 线
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.kline_service import save_klines
        fetcher = AKShareFetcher()
        klines = await fetcher.fetch_daily_kline(code, market=stock.market, days=200)
        saved_klines = await save_klines(db, code, klines)
        await db.commit()

        # 2. 重算指标
        from app.services.analysis.technical_analyzer import TechnicalAnalyzer
        analyzer = TechnicalAnalyzer()
        saved_indicators = await analyzer.calc_and_save(db, code)
        await db.commit()

        return {
            "message": "技术指标重算完成",
            "klines_saved": saved_klines,
            "indicators_saved": saved_indicators,
        }
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"重算失败: {e}")
