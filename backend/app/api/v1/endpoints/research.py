"""券商研报 API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.research import GlobalResearchReportRead, ResearchReportRead
from app.services import research_service

router = APIRouter()


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
