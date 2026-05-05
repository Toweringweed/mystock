"""技术信号事件检测

  - MACD_DIVERGENCE_NEW : 当日新增的 MACD/RSI 背离信号（divergence_signals 当日）
  - VOLUME_SPIKE        : 当日成交量 > 20 日均量 × 3
"""
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import DivergenceSignal
from app.models.kline import StockDailyKline
from app.models.stock import Stock
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)

VOLUME_SPIKE_MULTIPLIER = 3.0
MA20_DAYS = 20


async def detect_macd_divergence(db: AsyncSession, target_date: date | None = None) -> int:
    """检测当日新增的背离信号"""
    target = target_date or date.today()

    rows = await db.execute(
        select(DivergenceSignal, Stock.code, Stock.name)
        .join(Stock, Stock.id == DivergenceSignal.stock_id)
        .where(DivergenceSignal.detected_date == target)
        .where(Stock.is_watchlist.is_(True))
    )
    created = 0
    for sig, code, name in rows.all():
        is_bull = sig.signal_type.endswith("BULL")
        title = (
            f"{name}({code}) {'底背离' if is_bull else '顶背离'} "
            f"[{sig.signal_type}] 置信度 {sig.confidence or 0:.2f}"
        )
        ok = await upsert_event(
            db,
            stock_id=sig.stock_id,
            event_type="MACD_DIVERGENCE_NEW",
            severity="medium",
            dedup_key=f"{sig.signal_type}:{sig.detected_date.isoformat()}",
            title=title,
            payload={
                "signal_type": sig.signal_type,
                "detected_date": sig.detected_date.isoformat(),
                "confidence": float(sig.confidence) if sig.confidence else None,
                "price_point1": float(sig.price_point1) if sig.price_point1 else None,
                "price_point2": float(sig.price_point2) if sig.price_point2 else None,
            },
        )
        if ok:
            created += 1
    return created


async def detect_volume_spike(db: AsyncSession, target_date: date | None = None) -> int:
    """检测当日异常放量

    取自选股最新 K 线，与近 20 日均量对比。
    """
    target = target_date or date.today()
    lookback_start = target - timedelta(days=40)  # 40 个自然日，覆盖 20 个交易日

    stocks_rows = await db.execute(
        select(Stock.id, Stock.code, Stock.name).where(Stock.is_watchlist.is_(True))
    )
    created = 0
    for stock_id, code, name in stocks_rows.all():
        # 取近 20 日 K 线
        kline_rows = await db.execute(
            select(StockDailyKline)
            .where(StockDailyKline.stock_id == stock_id)
            .where(StockDailyKline.trade_date >= lookback_start)
            .where(StockDailyKline.trade_date <= target)
            .order_by(StockDailyKline.trade_date.desc())
            .limit(MA20_DAYS + 1)
        )
        klines = list(kline_rows.scalars().all())
        if len(klines) < MA20_DAYS + 1:
            continue
        latest = klines[0]
        if latest.trade_date != target:
            # 当日没有 K 线（非交易日）
            continue
        history = klines[1 : MA20_DAYS + 1]
        avg_vol = sum((k.volume or 0) for k in history) / len(history)
        if avg_vol <= 0 or not latest.volume:
            continue
        ratio = latest.volume / avg_vol
        if ratio < VOLUME_SPIKE_MULTIPLIER:
            continue

        title = (
            f"{name}({code}) 异常放量：当日量 {latest.volume:,} 手，"
            f"为 20 日均量的 {ratio:.1f} 倍"
        )
        ok = await upsert_event(
            db,
            stock_id=stock_id,
            event_type="VOLUME_SPIKE",
            severity="medium",
            dedup_key=f"vol:{target.isoformat()}",
            title=title,
            payload={
                "trade_date": target.isoformat(),
                "volume": latest.volume,
                "avg_20": round(avg_vol, 2),
                "ratio": round(ratio, 2),
                "change_pct": float(latest.change_pct) if latest.change_pct else None,
            },
        )
        if ok:
            created += 1
    return created


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    return (
        await detect_macd_divergence(db, target_date)
        + await detect_volume_spike(db, target_date)
    )
