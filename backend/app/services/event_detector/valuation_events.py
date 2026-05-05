"""估值异常事件检测

PE 历史百分位用近似法：当前 EPS-TTM × 5 年收盘价反推日级 PE 序列，
再用 PostgreSQL `percentile_cont` 在 SQL 层计算 5%/95% 阈值，
避免把 1250 行 × 50 只 = 62k 行回 Python。
"""
import logging
from datetime import date, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fundamental import StockFundamental
from app.models.kline import StockDailyKline
from app.models.stock import Stock
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)

LOW_PERCENTILE = 5.0
HIGH_PERCENTILE = 95.0
HISTORY_YEARS = 5


async def _emit_pe_event(
    db: AsyncSession,
    *,
    stock_id: int,
    code: str,
    name: str,
    target: date,
    cur_pe: float,
    low_thr: float,
    high_thr: float,
    pct: float,
    is_low: bool,
) -> bool:
    label = "跌破" if is_low else "突破"
    pctile = LOW_PERCENTILE if is_low else HIGH_PERCENTILE
    threshold = low_thr if is_low else high_thr
    return await upsert_event(
        db,
        stock_id=stock_id,
        event_type="PE_EXTREME_LOW" if is_low else "PE_EXTREME_HIGH",
        severity="medium",
        dedup_key=f"{'pe_low' if is_low else 'pe_high'}:{target.isoformat()}",
        title=(
            f"{name}({code}) PE-TTM={cur_pe:.2f} {label}近 {HISTORY_YEARS} 年 "
            f"{pctile:.0f}% 分位 ({threshold:.2f})"
        ),
        payload={
            "trade_date": target.isoformat(),
            "current_pe": cur_pe,
            "percentile": round(pct, 2),
            "low_threshold": round(low_thr, 2),
            "high_threshold": round(high_thr, 2),
            "history_years": HISTORY_YEARS,
        },
    )


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    target = target_date or date.today()
    cutoff = target - timedelta(days=HISTORY_YEARS * 365)

    rows = await db.execute(
        select(Stock.id, Stock.code, Stock.name).where(Stock.is_watchlist.is_(True))
    )
    created = 0
    for stock_id, code, name in rows.all():
        # 当前 PE-TTM 与 EPS-TTM
        f_row = await db.execute(
            select(StockFundamental.pe_ttm, StockFundamental.eps)
            .where(StockFundamental.stock_id == stock_id)
            .where(StockFundamental.period_type == "ttm")
            .order_by(StockFundamental.updated_at.desc())
            .limit(1)
        )
        record = f_row.one_or_none()
        if not record:
            continue
        current_pe, eps_ttm = record
        if not current_pe or not eps_ttm or float(eps_ttm) <= 0:
            continue

        eps_f = float(eps_ttm)
        cur_pe = float(current_pe)

        # 在 SQL 层一次计算两个分位数与样本计数，避免拉 1250 行回 Python
        pe_expr = StockDailyKline.close / eps_f
        stats_row = await db.execute(
            select(
                func.percentile_cont(LOW_PERCENTILE / 100.0)
                    .within_group(pe_expr.asc()).label("low_thr"),
                func.percentile_cont(HIGH_PERCENTILE / 100.0)
                    .within_group(pe_expr.asc()).label("high_thr"),
                func.count().label("n"),
                func.sum(case((pe_expr < cur_pe, 1), else_=0)).label("below_count"),
            )
            .where(StockDailyKline.stock_id == stock_id)
            .where(StockDailyKline.trade_date >= cutoff)
            .where(StockDailyKline.close.is_not(None))
        )
        stats = stats_row.one_or_none()
        if not stats or not stats.n or stats.n < 250:  # 至少 1 年数据
            continue

        low_thr = float(stats.low_thr)
        high_thr = float(stats.high_thr)
        pct = (float(stats.below_count) / float(stats.n)) * 100

        if cur_pe <= low_thr:
            if await _emit_pe_event(
                db, stock_id=stock_id, code=code, name=name, target=target,
                cur_pe=cur_pe, low_thr=low_thr, high_thr=high_thr, pct=pct, is_low=True,
            ):
                created += 1
        elif cur_pe >= high_thr:
            if await _emit_pe_event(
                db, stock_id=stock_id, code=code, name=name, target=target,
                cur_pe=cur_pe, low_thr=low_thr, high_thr=high_thr, pct=pct, is_low=False,
            ):
                created += 1
    return created
