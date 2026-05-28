"""券商研报 API"""
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.research import GlobalResearchReportRead, ResearchReportRead
from app.services import research_service

router = APIRouter()


# ── Claude Code Web Search 提交研报入库 ─────────────────────────────
class ManualResearchInput(BaseModel):
    """Claude Code Web Search 抓到的研报数据"""
    code: str
    broker: str
    title: str
    report_date: str                   # YYYY-MM-DD
    rating: str | None = None
    target_price: float | None = None
    forecast_year_base: int | None = None
    eps_y1: float | None = None
    eps_y2: float | None = None
    eps_y3: float | None = None
    pe_y1: float | None = None
    pe_y2: float | None = None
    pe_y3: float | None = None
    summary: str | None = None
    source_url: str | None = None


@router.post("/research/manual-add", tags=["research"])
async def add_manual_research(
    payload: ManualResearchInput,
    db: AsyncSession = Depends(get_db),
):
    """Claude Code Web Search 研报入库(industry_news + research_report_meta + relation)"""
    from app.models.news import IndustryNews, NewsStockRelation
    from app.models.research import ResearchReportMeta
    from app.models.stock import Stock

    res = await db.execute(select(Stock.id).where(Stock.code == payload.code))
    stock_id = res.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(404, f"股票 {payload.code} 不存在")

    try:
        published_at = datetime.strptime(payload.report_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(400, f"report_date 必须 YYYY-MM-DD: {payload.report_date}")

    hash_seed = f"claude_ws|{payload.broker}|{payload.code}|{payload.report_date}|{payload.title[:80]}"
    content_hash = hashlib.sha256(hash_seed.encode()).hexdigest()

    news_stmt = pg_insert(IndustryNews).values(
        title=payload.title[:500],
        summary=payload.summary,
        source="claude_web_search",
        source_url=payload.source_url,
        published_at=published_at,
        content_hash=content_hash,
        category="research",
        source_authority=0.80,
        related_industries=[],
    ).on_conflict_do_nothing(index_elements=["content_hash"])
    await db.execute(news_stmt)

    res = await db.execute(select(IndustryNews.id).where(IndustryNews.content_hash == content_hash))
    news_id = res.scalar_one_or_none()
    if not news_id:
        return {"ok": True, "duplicate": True, "code": payload.code}

    # target_price 没 EPS/PE 时用 fake (target_price, 1.0) 让 EPS×PE 推算 = target_price
    eps_y1 = payload.eps_y1
    pe_y1 = payload.pe_y1
    if payload.target_price and (eps_y1 is None or pe_y1 is None):
        eps_y1 = float(payload.target_price)
        pe_y1 = 1.0

    meta_stmt = pg_insert(ResearchReportMeta).values(
        news_id=news_id,
        stock_id=stock_id,
        broker=payload.broker[:64],
        rating=(payload.rating or None),
        forecast_year_base=payload.forecast_year_base,
        eps_y1=eps_y1, eps_y2=payload.eps_y2, eps_y3=payload.eps_y3,
        pe_y1=pe_y1, pe_y2=payload.pe_y2, pe_y3=payload.pe_y3,
        pdf_url=payload.source_url,
    ).on_conflict_do_nothing(index_elements=["news_id"])
    await db.execute(meta_stmt)

    rel_stmt = pg_insert(NewsStockRelation).values(
        news_id=news_id, stock_id=stock_id, relevance=1.0,
    ).on_conflict_do_nothing()
    await db.execute(rel_stmt)

    await db.commit()
    return {"ok": True, "news_id": news_id, "code": payload.code, "broker": payload.broker}


@router.get(
    "/research",
    response_model=list[GlobalResearchReportRead],
    tags=["research"],
)
async def list_global_research(
    code: str | None = Query(None, description="股票代码"),
    broker: str | None = Query(None, description="机构名"),
    rating: str | None = Query(None, description="东财评级"),
    days: int = Query(30, ge=1, le=365, description="近 N 天"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """全局研报库（支持按股票/机构/评级/日期范围筛选）"""
    return await research_service.list_global(
        db, code=code, broker=broker, rating=rating, days=days, limit=limit,
    )


@router.get(
    "/research/brokers",
    response_model=list[str],
    tags=["research"],
)
async def list_research_brokers(
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """近 N 天出现过的机构（用于前端筛选下拉）"""
    return await research_service.list_brokers(db, days=days)


@router.get(
    "/stocks/{code}/research",
    response_model=list[ResearchReportRead],
    tags=["research"],
)
async def get_stock_research(
    code: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """单只股票最近的券商研报（按发布日期 desc）"""
    return await research_service.list_for_stock(db, code, limit=limit)


@router.post(
    "/stocks/{code}/research/refresh",
    status_code=202,
    tags=["research"],
)
async def refresh_stock_research(code: str):
    """触发该股票研报的即时抓取（按需，不等待）"""
    from app.tasks.news_tasks import crawl_research_reports
    crawl_research_reports.delay()
    return {"message": "研报抓取任务已提交（全量）"}
