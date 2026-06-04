"""背离信号检测与查询服务"""
import logging
from datetime import date, timedelta

import numpy as np
from scipy.signal import find_peaks
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import DivergenceSignal
from app.models.stock import Stock

logger = logging.getLogger(__name__)

LOOKBACK = 60     # 回看交易日数
MIN_PEAK_DIST = 5 # 极值点最小间隔（交易日）


async def _get_stock_id(db: AsyncSession, code: str) -> int | None:
    result = await db.execute(select(Stock.id).where(Stock.code == code))
    return result.scalar_one_or_none()


def _detect_divergence(
    prices: np.ndarray,
    indicator: np.ndarray,
    dates: list,
    signal_prefix: str,
) -> list[dict]:
    """
    检测价格与指标之间的背离
    - 顶背离（BEAR）: 价格新高，指标未新高
    - 底背离（BULL）: 价格新低，指标未新低
    """
    signals = []
    n = len(prices)
    if n < 20:
        return signals

    # 检测价格和指标的极值点
    price_highs, _ = find_peaks(prices, distance=MIN_PEAK_DIST, prominence=prices.std() * 0.3)
    price_lows, _ = find_peaks(-prices, distance=MIN_PEAK_DIST, prominence=prices.std() * 0.3)
    ind_highs, _ = find_peaks(indicator, distance=MIN_PEAK_DIST)
    ind_lows, _ = find_peaks(-indicator, distance=MIN_PEAK_DIST)

    # 顶背离：最近两个价格高点，价格创新高但指标未创新高
    if len(price_highs) >= 2:
        p1, p2 = price_highs[-2], price_highs[-1]
        if prices[p2] > prices[p1]:  # 价格新高
            # 找指标对应附近的高点
            ind_near_p2 = [i for i in ind_highs if abs(i - p2) <= 5]
            ind_near_p1 = [i for i in ind_highs if abs(i - p1) <= 5]
            if ind_near_p2 and ind_near_p1:
                ind_val_p2 = indicator[max(ind_near_p2, key=lambda x: indicator[x])]
                ind_val_p1 = indicator[max(ind_near_p1, key=lambda x: indicator[x])]
                if ind_val_p2 < ind_val_p1:  # 指标未新高 → 顶背离
                    price_diff = (prices[p2] - prices[p1]) / prices[p1]
                    ind_diff = (ind_val_p1 - ind_val_p2) / abs(ind_val_p1) if ind_val_p1 else 0
                    confidence = min(1.0, (price_diff + ind_diff) / 2 + 0.3)
                    signals.append({
                        "signal_type": f"{signal_prefix}_BEAR",
                        "detected_date": dates[p2] if p2 < len(dates) else date.today(),
                        "price_point1": float(prices[p1]),
                        "price_point2": float(prices[p2]),
                        "indicator_point1": float(ind_val_p1),
                        "indicator_point2": float(ind_val_p2),
                        "confidence": round(float(confidence), 3),
                    })

    # 底背离：最近两个价格低点，价格创新低但指标未创新低
    if len(price_lows) >= 2:
        p1, p2 = price_lows[-2], price_lows[-1]
        if prices[p2] < prices[p1]:  # 价格新低
            ind_near_p2 = [i for i in ind_lows if abs(i - p2) <= 5]
            ind_near_p1 = [i for i in ind_lows if abs(i - p1) <= 5]
            if ind_near_p2 and ind_near_p1:
                ind_val_p2 = indicator[min(ind_near_p2, key=lambda x: indicator[x])]
                ind_val_p1 = indicator[min(ind_near_p1, key=lambda x: indicator[x])]
                if ind_val_p2 > ind_val_p1:  # 指标未新低 → 底背离
                    price_diff = (prices[p1] - prices[p2]) / prices[p1]
                    ind_diff = (ind_val_p2 - ind_val_p1) / abs(ind_val_p1) if ind_val_p1 else 0
                    confidence = min(1.0, (price_diff + ind_diff) / 2 + 0.3)
                    signals.append({
                        "signal_type": f"{signal_prefix}_BULL",
                        "detected_date": dates[p2] if p2 < len(dates) else date.today(),
                        "price_point1": float(prices[p1]),
                        "price_point2": float(prices[p2]),
                        "indicator_point1": float(ind_val_p1),
                        "indicator_point2": float(ind_val_p2),
                        "confidence": round(float(confidence), 3),
                    })

    return signals


async def calc_and_save_divergence(db: AsyncSession, code: str) -> list[DivergenceSignal]:
    """计算并保存背离信号"""
    from app.services.kline_service import get_indicators, get_kline_dataframe

    df = await get_kline_dataframe(db, code, days=LOOKBACK + 10)
    indicators = await get_indicators(db, code, days=LOOKBACK + 10)

    if df.empty or len(indicators) < 20:
        return []

    df["close"].values
    dates = list(df.index.date)

    # 对齐 indicators 与 prices（按日期）
    ind_dict = {ind.trade_date: ind for ind in indicators}
    aligned_dates = [d for d in dates if d in ind_dict]
    if len(aligned_dates) < 20:
        return []

    aligned_prices = np.array([float(df.loc[str(d)]["close"]) for d in aligned_dates])
    macd_hist = np.array([float(ind_dict[d].macd_hist or 0) for d in aligned_dates])
    rsi14 = np.array([float(ind_dict[d].rsi_14 or 50) for d in aligned_dates])

    all_signals: list[dict] = []
    all_signals.extend(_detect_divergence(aligned_prices, macd_hist, aligned_dates, "MACD"))
    all_signals.extend(_detect_divergence(aligned_prices, rsi14, aligned_dates, "RSI"))

    if not all_signals:
        return []

    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return []

    saved = []
    for sig in all_signals:
        stmt = insert(DivergenceSignal).values(stock_id=stock_id, **sig)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["stock_id", "signal_type", "detected_date"]
        )
        await db.execute(stmt)

    await db.flush()
    logger.info(f"[{code}] 背离信号检测完成，发现 {len(all_signals)} 个信号")
    return saved


async def get_divergence(
    db: AsyncSession, code: str, days: int = 60
) -> list[DivergenceSignal]:
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return []
    since = date.today() - timedelta(days=days)
    result = await db.execute(
        select(DivergenceSignal)
        .where(
            DivergenceSignal.stock_id == stock_id,
            DivergenceSignal.detected_date >= since,
        )
        .order_by(DivergenceSignal.detected_date.desc())
    )
    return list(result.scalars().all())
