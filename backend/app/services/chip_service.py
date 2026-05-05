"""筹码分布计算与存取服务（GSY 模型）"""
import logging
from datetime import date

import numpy as np
from scipy.stats import norm
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analysis import ChipDistribution
from app.models.stock import Stock

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 250   # 筹码回看交易日数
PRICE_BINS = 100      # 价格区间数量


async def _get_stock_id(db: AsyncSession, code: str) -> int | None:
    result = await db.execute(select(Stock.id).where(Stock.code == code))
    return result.scalar_one_or_none()


def calc_chip_distribution(df) -> dict:
    """
    GSY 模型计算筹码分布
    df: pandas DataFrame，index=trade_date，columns 含 high/low/close/turnover
    """
    if df.empty or len(df) < 10:
        return {}

    price_min = float(df["low"].min())
    price_max = float(df["high"].max())
    if price_min >= price_max:
        return {}

    price_bins = np.linspace(price_min, price_max, PRICE_BINS)
    chip_array = np.zeros(PRICE_BINS)

    # 优先用换手率，没有则用成交量归一化代替
    has_turnover = df["turnover"].notna().any() and (df["turnover"] > 0).any()
    if not has_turnover:
        total_vol = df["volume"].sum()
        if total_vol <= 0:
            return {}

    for _, row in df.iterrows():
        if has_turnover:
            turnover = float(row.get("turnover", 0) or 0) / 100  # 换手率 % → 小数
            if turnover <= 0:
                continue
            turnover = min(turnover, 1.0)
        else:
            vol = float(row.get("volume", 0) or 0)
            if vol <= 0:
                continue
            turnover = min(vol / total_vol * len(df) * 0.02, 1.0)  # 模拟换手率

        # 当日成交均价
        avg_price = (float(row["high"]) + float(row["low"]) + float(row["close"])) / 3
        spread = max(float(row["high"]) - float(row["low"]), price_max * 0.001)

        # 按正态分布模拟当日成交分布
        distribution = norm.pdf(price_bins, avg_price, spread / 3)
        dist_sum = distribution.sum()
        if dist_sum > 0:
            distribution = distribution / dist_sum * turnover

        # 旧筹码衰减，新筹码叠加
        chip_array = chip_array * (1 - turnover) + distribution

    # 归一化
    total = chip_array.sum()
    if total <= 0:
        return {}
    chip_array = chip_array / total

    current_price = float(df["close"].iloc[-1])
    profit_mask = price_bins < current_price
    profit_ratio = float(chip_array[profit_mask].sum())
    avg_cost = float(np.average(price_bins, weights=chip_array))

    # 集中度：包含 90% 筹码的最窄连续价格区间宽度 / 当前价，以百分比表示
    # 用双指针滑动窗口在价格有序区间上寻找最小覆盖范围
    target = 0.9
    bin_width = (price_max - price_min) / (PRICE_BINS - 1) if PRICE_BINS > 1 else 0
    best_width = price_max - price_min  # 最差情况：全价格范围
    window_sum = 0.0
    left = 0
    for right in range(PRICE_BINS):
        window_sum += chip_array[right]
        # 收缩左边界：当窗口去掉左端仍满足条件时，继续收缩
        while window_sum - chip_array[left] >= target:
            window_sum -= chip_array[left]
            left += 1
        if window_sum >= target:
            width = price_bins[right] - price_bins[left] + bin_width
            if width < best_width:
                best_width = width
    concentration = best_width / current_price * 100 if current_price > 0 else 100.0

    # 构建价格区间列表
    bin_width = (price_max - price_min) / PRICE_BINS
    price_ranges = [
        {
            "price_low": round(float(price_bins[i]), 3),
            "price_high": round(float(price_bins[i]) + bin_width, 3),
            "chip_pct": round(float(chip_array[i]), 6),
        }
        for i in range(PRICE_BINS)
    ]

    return {
        "price_ranges": price_ranges,
        "profit_ratio": round(profit_ratio, 4),
        "avg_cost": round(avg_cost, 3),
        "concentration": round(concentration, 2),
    }


async def calc_and_save_chip(db: AsyncSession, code: str) -> ChipDistribution | None:
    """计算并保存今日筹码分布，同时回填近30日历史（供日度快照表使用）"""
    from app.services.kline_service import get_kline_dataframe

    df = await get_kline_dataframe(db, code, days=LOOKBACK_DAYS + 30)
    if df.empty:
        return None

    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return None

    # 回填近30日历史筹码（只补缺失日期，已有数据不重算）
    await _backfill_chip_history(db, stock_id, df, backfill_days=30)

    # 当日完整计算（总是更新）
    result = calc_chip_distribution(df)
    if not result:
        return None

    today = date.today()
    stmt = insert(ChipDistribution).values(
        stock_id=stock_id,
        calc_date=today,
        **result,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id", "calc_date"],
        set_={k: stmt.excluded[k] for k in result},
    )
    await db.execute(stmt)
    await db.flush()
    logger.info(f"[{code}] 筹码分布计算完成，获利盘: {result['profit_ratio']:.1%}")

    res = await db.execute(
        select(ChipDistribution).where(
            ChipDistribution.stock_id == stock_id,
            ChipDistribution.calc_date == today,
        )
    )
    return res.scalar_one_or_none()


async def _backfill_chip_history(
    db: AsyncSession, stock_id: int, full_df, backfill_days: int = 30
) -> None:
    """
    为近 backfill_days 个交易日回填筹码快照（跳过已有数据的日期）。
    对每个历史日期，截取到该日的 K 线子集来模拟当时的筹码分布。
    """
    if full_df.empty:
        return

    # 取最近 backfill_days 个交易日（不含今天，今天由调用方单独写）
    today = date.today()
    trade_dates = [d.date() for d in full_df.index if d.date() < today]
    target_dates = trade_dates[-backfill_days:]
    if not target_dates:
        return

    # 查询已有记录
    existing = await db.execute(
        select(ChipDistribution.calc_date).where(
            ChipDistribution.stock_id == stock_id,
            ChipDistribution.calc_date.in_(target_dates),
        )
    )
    existing_dates = {r[0] for r in existing.fetchall()}
    missing_dates = [d for d in target_dates if d not in existing_dates]
    if not missing_dates:
        return

    rows = []
    for calc_date in missing_dates:
        # 截取到该日的数据，用于模拟当日筹码
        sub_df = full_df[full_df.index.date <= calc_date]
        if len(sub_df) < 10:
            continue
        result = calc_chip_distribution(sub_df)
        if not result:
            continue
        rows.append({
            "stock_id": stock_id,
            "calc_date": calc_date,
            **result,
        })

    if rows:
        stmt = insert(ChipDistribution).values(rows)
        stmt = stmt.on_conflict_do_nothing(index_elements=["stock_id", "calc_date"])
        await db.execute(stmt)
        await db.flush()
        logger.info(f"[stock_id={stock_id}] 历史筹码回填 {len(rows)} 条")


async def get_chip(db: AsyncSession, code: str) -> ChipDistribution | None:
    stock_id = await _get_stock_id(db, code)
    if not stock_id:
        return None
    result = await db.execute(
        select(ChipDistribution)
        .where(ChipDistribution.stock_id == stock_id)
        .order_by(ChipDistribution.calc_date.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
