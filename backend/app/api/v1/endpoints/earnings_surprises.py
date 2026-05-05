"""财报预期差 API — Skill 写入 + 历史查询 + 即将披露日历"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.calendar_event import CalendarEvent
from app.models.earnings_surprise import EarningsSurprise
from app.models.kline import StockDailyKline
from app.models.stock import Stock
from app.schemas.earnings_surprise import (
    EarningsSurpriseInput, EarningsSurpriseRead, UpcomingEarningsItem,
)

router = APIRouter()


# ────────────────────── helpers ──────────────────────

async def _resolve_stock_id(db: AsyncSession, code: str) -> int:
    res = await db.execute(select(Stock.id).where(Stock.code == code))
    sid = res.scalar_one_or_none()
    if not sid:
        raise HTTPException(404, f"股票 {code} 不存在")
    return sid


async def _compute_returns(
    db: AsyncSession, stock_id: int, release_date: date,
) -> dict[str, Decimal | None]:
    """从 stock_daily_kline 计算财报前后窗口涨跌幅."""
    # 找披露日及之后第一个交易日的收盘价(含披露日)
    res = await db.execute(
        select(StockDailyKline.close, StockDailyKline.trade_date)
        .where(StockDailyKline.stock_id == stock_id)
        .where(StockDailyKline.trade_date >= release_date)
        .order_by(StockDailyKline.trade_date.asc())
        .limit(1)
    )
    row = res.first()
    if not row:
        return {}
    base_price = float(row.close)
    base_date = row.trade_date

    # 披露前 N 日(取披露日前一交易日)
    res = await db.execute(
        select(StockDailyKline.close)
        .where(StockDailyKline.stock_id == stock_id)
        .where(StockDailyKline.trade_date < release_date)
        .order_by(StockDailyKline.trade_date.desc())
        .limit(1)
    )
    prev = res.first()
    pre_anchor_price = float(prev.close) if prev else None

    # 计算窗口收益:取离 anchor + N 个交易日最近的价
    async def _window_return(anchor_date: date, n_days: int, direction: int = 1) -> Decimal | None:
        """direction=+1 向后 N 日,-1 向前 N 日."""
        target_date = anchor_date + timedelta(days=n_days * direction)
        if direction > 0:
            q = await db.execute(
                select(StockDailyKline.close)
                .where(StockDailyKline.stock_id == stock_id)
                .where(StockDailyKline.trade_date <= target_date)
                .where(StockDailyKline.trade_date > anchor_date)
                .order_by(StockDailyKline.trade_date.desc())
                .limit(1)
            )
        else:
            q = await db.execute(
                select(StockDailyKline.close)
                .where(StockDailyKline.stock_id == stock_id)
                .where(StockDailyKline.trade_date >= target_date)
                .where(StockDailyKline.trade_date < anchor_date)
                .order_by(StockDailyKline.trade_date.asc())
                .limit(1)
            )
        r = q.first()
        if not r:
            return None
        try:
            return Decimal(str(round((float(r.close) - base_price) / base_price * 100, 2)))
        except (ZeroDivisionError, TypeError):
            return None

    out: dict[str, Decimal | None] = {
        "price_at_release": Decimal(str(base_price)),
    }

    # post-release 1d/5d/30d
    out["post_release_1d_return"] = await _window_return(base_date, 1, +1)
    out["post_release_5d_return"] = await _window_return(base_date, 7, +1)  # 5 交易日 ≈ 7 日历日
    out["post_release_30d_return"] = await _window_return(base_date, 42, +1)  # 30 交易日 ≈ 42 日历日

    # pre-release 5d/20d (从 base 向前)
    if pre_anchor_price:
        out["pre_release_5d_return"] = await _window_return(base_date, 7, -1)
        out["pre_release_20d_return"] = await _window_return(base_date, 28, -1)

    return out


def _classify_surprise(pct: Decimal | None) -> str | None:
    if pct is None:
        return None
    p = float(pct)
    if p >= 5:
        return "beat"
    if p <= -5:
        return "miss"
    return "meet"


# ────────────────────── endpoints ──────────────────────

@router.post(
    "/stocks/{code}/earnings-surprises",
    response_model=EarningsSurpriseRead,
    tags=["earnings"],
)
async def upsert_earnings_surprise(
    code: str,
    payload: EarningsSurpriseInput,
    db: AsyncSession = Depends(get_db),
):
    """
    Upsert 一条财报预期差记录(基于 stock_id + period_type + period 唯一约束)。

    自动行为:
    - 如未传 surprise_revenue_pct/net_profit_pct,从 expected/actual 自动算
    - 如未传 surprise_direction,从 surprise_net_profit_pct 自动分类(>5% beat / <-5% miss / 中间 meet)
    - 如未传 pre/post_release_*_return,自动从 stock_daily_kline 算
    """
    stock_id = await _resolve_stock_id(db, code)
    values = payload.model_dump()
    values["stock_id"] = stock_id
    values["updated_at"] = datetime.utcnow()

    # 自动算 surprise %
    def _auto_pct(actual_key: str, expected_key: str, pct_key: str):
        if values.get(pct_key) is not None:
            return
        a = values.get(actual_key)
        e = values.get(expected_key)
        if a is not None and e is not None and Decimal(str(e)) != 0:
            values[pct_key] = Decimal(
                str(round((float(a) - float(e)) / float(e) * 100, 2))
            )

    _auto_pct("actual_revenue_yi", "expected_revenue_yi", "surprise_revenue_pct")
    _auto_pct("actual_net_profit_yi", "expected_net_profit_yi", "surprise_net_profit_pct")

    if values.get("surprise_direction") is None:
        values["surprise_direction"] = _classify_surprise(values.get("surprise_net_profit_pct"))

    # 自动算股价反应(若未传)
    needs_returns = any(
        values.get(k) is None for k in (
            "price_at_release", "post_release_5d_return", "post_release_30d_return"
        )
    )
    if needs_returns:
        auto_returns = await _compute_returns(db, stock_id, payload.release_date)
        for k, v in auto_returns.items():
            if values.get(k) is None and v is not None:
                values[k] = v

    stmt = pg_insert(EarningsSurprise).values(**values)
    update_cols = {
        k: stmt.excluded[k] for k in values.keys()
        if k not in ("stock_id", "period_type", "period", "created_at")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_earnings_surprise_stock_period",
        set_=update_cols,
    ).returning(EarningsSurprise.id)

    res = await db.execute(stmt)
    row_id = res.scalar_one()
    await db.commit()

    out = await db.execute(
        select(EarningsSurprise).where(EarningsSurprise.id == row_id)
    )
    return out.scalar_one()


@router.get(
    "/stocks/{code}/earnings-surprises",
    response_model=list[EarningsSurpriseRead],
    tags=["earnings"],
)
async def list_stock_earnings_surprises(
    code: str,
    limit: int = Query(12, ge=1, le=40),
    db: AsyncSession = Depends(get_db),
):
    """单股票历史财报预期差(按披露日 desc)."""
    stock_id = await _resolve_stock_id(db, code)
    res = await db.execute(
        select(EarningsSurprise)
        .where(EarningsSurprise.stock_id == stock_id)
        .order_by(EarningsSurprise.release_date.desc())
        .limit(limit)
    )
    return res.scalars().all()


@router.get(
    "/earnings-surprises/upcoming",
    response_model=list[UpcomingEarningsItem],
    tags=["earnings"],
)
async def upcoming_earnings(
    days: int = Query(60, ge=1, le=180),
    only_watchlist: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    """
    即将到来的财报披露(从 calendar_events.event_type='earnings_release' 取),
    含上次披露的 surprise 方向(用于判断"连续超预期 / 连续低预期")。
    """
    today = date.today()
    cutoff = today + timedelta(days=days)

    stmt = (
        select(CalendarEvent, Stock)
        .join(Stock, Stock.id == CalendarEvent.stock_id)
        .where(CalendarEvent.event_type == "earnings_release")
        .where(CalendarEvent.event_date >= today)
        .where(CalendarEvent.event_date <= cutoff)
    )
    if only_watchlist:
        stmt = stmt.where(Stock.is_watchlist.is_(True))
    stmt = stmt.order_by(CalendarEvent.event_date.asc()).limit(80)
    res = await db.execute(stmt)

    items: list[UpcomingEarningsItem] = []
    for ev, st in res.all():
        # 取上次 surprise
        last_q = await db.execute(
            select(EarningsSurprise.surprise_direction, EarningsSurprise.surprise_net_profit_pct)
            .where(EarningsSurprise.stock_id == st.id)
            .order_by(EarningsSurprise.release_date.desc())
            .limit(1)
        )
        last = last_q.first()
        items.append(UpcomingEarningsItem(
            stock_id=st.id,
            code=st.code,
            name=st.name,
            expected_release_date=ev.event_date,
            days_to_release=(ev.event_date - today).days,
            period_hint=(ev.payload or {}).get("period") if isinstance(ev.payload, dict) else None,
            last_surprise_direction=last.surprise_direction if last else None,
            last_surprise_pct=last.surprise_net_profit_pct if last else None,
        ))
    return items


@router.get(
    "/earnings-surprises/recent",
    response_model=list[EarningsSurpriseRead],
    tags=["earnings"],
)
async def recent_earnings_surprises(
    days: int = Query(60, ge=1, le=180),
    direction: str | None = Query(None, description="beat / meet / miss"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """全市场最近披露的财报 + surprise 排行(按披露日 desc)."""
    cutoff = date.today() - timedelta(days=days)
    conds = [EarningsSurprise.release_date >= cutoff]
    if direction:
        conds.append(EarningsSurprise.surprise_direction == direction)
    res = await db.execute(
        select(EarningsSurprise)
        .where(and_(*conds))
        .order_by(EarningsSurprise.release_date.desc())
        .limit(limit)
    )
    return res.scalars().all()
