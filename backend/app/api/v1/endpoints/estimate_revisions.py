"""分析师 EPS / 目标价共识修正 API"""
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.estimate_revision import EstimateRevision
from app.models.stock import Stock
from app.schemas.estimate_revision import EstimateRevisionInput, EstimateRevisionRead

router = APIRouter()


async def _resolve_stock_id(db: AsyncSession, code: str) -> int:
    res = await db.execute(select(Stock.id).where(Stock.code == code))
    sid = res.scalar_one_or_none()
    if not sid:
        raise HTTPException(404, f"股票 {code} 不存在")
    return sid


def _classify_direction(pct: Decimal | None) -> str | None:
    if pct is None:
        return None
    p = float(pct)
    if p >= 1.0:
        return "up"
    if p <= -1.0:
        return "down"
    return "flat"


@router.post(
    "/stocks/{code}/estimate-revisions",
    response_model=EstimateRevisionRead,
    tags=["estimates"],
)
async def upsert_estimate_revision(
    code: str,
    payload: EstimateRevisionInput,
    db: AsyncSession = Depends(get_db),
):
    """
    Upsert 一条共识修正快照。自动算:
    - eps_revision_pct / net_profit_revision_pct / target_price_revision_pct(对比上一快照)
    - revision_direction(>+1% up / -1%~+1% flat / <-1% down)
    """
    stock_id = await _resolve_stock_id(db, code)
    values = payload.model_dump()
    values["stock_id"] = stock_id
    values["updated_at"] = datetime.utcnow()

    # 找上一快照(同 stock_id + forecast_year + 早于本次 revision_date)
    prev_q = await db.execute(
        select(EstimateRevision)
        .where(EstimateRevision.stock_id == stock_id)
        .where(EstimateRevision.forecast_year == payload.forecast_year)
        .where(EstimateRevision.revision_date < payload.revision_date)
        .order_by(EstimateRevision.revision_date.desc())
        .limit(1)
    )
    prev = prev_q.scalar_one_or_none()

    def _auto_revision(curr_key: str, prev_attr: str, pct_key: str):
        if values.get(pct_key) is not None:
            return
        curr = values.get(curr_key)
        if curr is None or prev is None:
            return
        prev_val = getattr(prev, prev_attr, None)
        if prev_val is None or float(prev_val) == 0:
            return
        values[pct_key] = Decimal(
            str(round((float(curr) - float(prev_val)) / float(prev_val) * 100, 2))
        )

    _auto_revision("consensus_eps", "consensus_eps", "eps_revision_pct")
    _auto_revision("consensus_net_profit_yi", "consensus_net_profit_yi", "net_profit_revision_pct")
    _auto_revision("consensus_target_price", "consensus_target_price", "target_price_revision_pct")

    if values.get("revision_direction") is None:
        # 优先用 EPS 修正方向,无则用净利润
        values["revision_direction"] = _classify_direction(
            values.get("eps_revision_pct") or values.get("net_profit_revision_pct")
        )

    stmt = pg_insert(EstimateRevision).values(**values)
    update_cols = {
        k: stmt.excluded[k] for k in values.keys()
        if k not in ("stock_id", "revision_date", "forecast_year", "created_at")
    }
    stmt = stmt.on_conflict_do_update(
        constraint="uq_estimate_revision_stock_date_year",
        set_=update_cols,
    ).returning(EstimateRevision.id)

    res = await db.execute(stmt)
    row_id = res.scalar_one()
    await db.commit()

    out = await db.execute(select(EstimateRevision).where(EstimateRevision.id == row_id))
    return out.scalar_one()


@router.get(
    "/stocks/{code}/estimate-revisions",
    response_model=list[EstimateRevisionRead],
    tags=["estimates"],
)
async def list_stock_revisions(
    code: str,
    forecast_year: int | None = Query(None),
    limit: int = Query(24, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
):
    """单股票历史共识修正(按 revision_date desc)"""
    stock_id = await _resolve_stock_id(db, code)
    stmt = select(EstimateRevision).where(EstimateRevision.stock_id == stock_id)
    if forecast_year:
        stmt = stmt.where(EstimateRevision.forecast_year == forecast_year)
    stmt = stmt.order_by(EstimateRevision.revision_date.desc()).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()
