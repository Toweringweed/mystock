"""外资/中资研报 API — Skill 自动写入入口"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.analyst_report import AnalystReport
from app.models.stock import Stock
from app.schemas.analyst_report import (
    AnalystReportBulkInput,
    AnalystReportBulkResult,
    AnalystReportRead,
)

router = APIRouter()


async def _resolve_stock_id(db: AsyncSession, code: str) -> int:
    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")
    return stock_id


@router.post(
    "/stocks/{code}/analyst-reports",
    response_model=AnalystReportBulkResult,
    tags=["analyst-reports"],
)
async def upsert_analyst_reports(
    code: str,
    payload: AnalystReportBulkInput,
    db: AsyncSession = Depends(get_db),
):
    """
    批量 upsert 研报(外资/中资均可)。

    - UNIQUE (stock_id, institution, report_date) → 同机构同日重复 POST 自动 UPDATE
    - 用 PostgreSQL ON CONFLICT 实现 upsert,保证幂等
    - 返回插入/更新计数 + 全量记录(已 refresh)
    """
    stock_id = await _resolve_stock_id(db, code)

    if not payload.reports:
        return AnalystReportBulkResult(inserted=0, updated=0, reports=[])

    inserted = 0
    updated = 0
    saved_ids: list[int] = []

    for item in payload.reports:
        values = item.model_dump()
        values["stock_id"] = stock_id
        values["updated_at"] = datetime.utcnow()

        stmt = pg_insert(AnalystReport).values(**values)
        # ON CONFLICT 时刷新所有非键字段(stock_id/institution/report_date 是冲突键,不更新)
        update_cols = {
            k: stmt.excluded[k]
            for k in values.keys()
            if k not in ("stock_id", "institution", "report_date", "created_at")
        }
        stmt = stmt.on_conflict_do_update(
            constraint="uq_analyst_report_stock_inst_date",
            set_=update_cols,
        ).returning(AnalystReport.id, AnalystReport.created_at, AnalystReport.updated_at)

        res = await db.execute(stmt)
        row = res.one()
        saved_ids.append(row.id)
        # created_at == updated_at 表示新插入(允许 < 1s 误差)
        if (row.updated_at - row.created_at).total_seconds() < 1.0:
            inserted += 1
        else:
            updated += 1

    await db.commit()

    # 重新查询全量返回(保证 ORM 序列化字段全)
    result = await db.execute(
        select(AnalystReport).where(AnalystReport.id.in_(saved_ids))
        .order_by(AnalystReport.report_date.desc())
    )
    reports = result.scalars().all()

    return AnalystReportBulkResult(
        inserted=inserted,
        updated=updated,
        reports=[AnalystReportRead.model_validate(r) for r in reports],
    )


@router.get(
    "/stocks/{code}/analyst-reports",
    response_model=list[AnalystReportRead],
    tags=["analyst-reports"],
)
async def list_stock_analyst_reports(
    code: str,
    is_foreign: bool | None = Query(None, description="筛选外资研报"),
    days: int = Query(180, ge=1, le=730, description="近 N 天"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """单只股票的研报列表(按报告日期倒序)"""
    stock_id = await _resolve_stock_id(db, code)

    cutoff = (datetime.utcnow() - timedelta(days=days)).date()
    conditions = [
        AnalystReport.stock_id == stock_id,
        AnalystReport.report_date >= cutoff,
    ]
    if is_foreign is not None:
        conditions.append(AnalystReport.is_foreign == is_foreign)

    stmt = (
        select(AnalystReport)
        .where(and_(*conditions))
        .order_by(AnalystReport.report_date.desc(), AnalystReport.updated_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get(
    "/analyst-reports/recent",
    response_model=list[AnalystReportRead],
    tags=["analyst-reports"],
)
async def list_recent_analyst_reports(
    is_foreign: bool | None = Query(None),
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """全市场最新研报流(可筛选外资)"""
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()
    conditions = [AnalystReport.report_date >= cutoff]
    if is_foreign is not None:
        conditions.append(AnalystReport.is_foreign == is_foreign)

    stmt = (
        select(AnalystReport)
        .where(and_(*conditions))
        .order_by(AnalystReport.report_date.desc(), AnalystReport.updated_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    return res.scalars().all()
