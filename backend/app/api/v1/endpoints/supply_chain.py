from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.supply_chain import (
    GlobalSupplyChainResponse,
    SupplyChainCoverageResponse,
    SupplyChainRead,
)

router = APIRouter()


@router.get("/global", response_model=GlobalSupplyChainResponse)
async def get_global_supply_chain_endpoint(db: AsyncSession = Depends(get_db)):
    """聚合所有自选股的上下游关系 → 全局供应链网络图。

    返回包含:
    - watchlist_stocks: 自选股节点(主)
    - external_companies: 外部上下游伙伴(非自选股)
    - edges: 上游→下游有向边
    - industry_groups: 自选股按行业聚簇分组
    """
    from app.services.supply_chain_service import get_global_supply_chain
    return await get_global_supply_chain(db)


@router.get("/global/coverage", response_model=SupplyChainCoverageResponse)
async def get_supply_chain_coverage_endpoint(db: AsyncSession = Depends(get_db)):
    """审计自选股供应链覆盖率。"""
    from app.services.supply_chain_service import get_supply_chain_coverage

    return await get_supply_chain_coverage(db)


@router.post("/global/fill-gaps", status_code=202)
async def fill_supply_chain_gaps_endpoint(limit: int = 10, force: bool = False):
    """批量排队补齐缺失的自选股供应链关系。"""
    from app.tasks.supply_chain_tasks import backfill_watchlist_supply_chains

    backfill_watchlist_supply_chains.delay(limit=limit, force=force)
    return {"message": f"供应链缺口补齐任务已提交，最多排队 {limit} 只", "force": force}


@router.post("/global/refresh-intelligence", status_code=202)
async def refresh_supply_chain_intelligence_endpoint(days: int = 14):
    """同步实体关系并回填近期资讯匹配。"""
    from app.tasks.supply_chain_tasks import refresh_supply_chain_intelligence

    refresh_supply_chain_intelligence.delay(days=days)
    return {"message": f"供应链智能层刷新任务已提交，回填近 {days} 天资讯"}


@router.get("/{code}", response_model=SupplyChainRead)
async def get_supply_chain(code: str, db: AsyncSession = Depends(get_db)):
    """获取单股供应链上下游数据"""
    from app.services.supply_chain_service import get_supply_chain as _get
    return await _get(db, code)


@router.post("/{code}/refresh", status_code=202)
async def refresh_supply_chain(code: str):
    """触发重新提取供应链（下载最新年报并 AI 解析）"""
    from app.tasks.supply_chain_tasks import extract_supply_chain_task
    extract_supply_chain_task.delay(code, use_annual_report=True)
    return {"message": "供应链提取任务已提交"}


@router.post("/global/materialize", status_code=202)
async def materialize_supply_chain_graph_endpoint():
    """将现有 supply_chains 旧关系同步到实体化供应链图谱表。"""
    from app.tasks.supply_chain_tasks import materialize_supply_chain_graph

    materialize_supply_chain_graph.delay()
    return {"message": "供应链实体图谱同步任务已提交"}


@router.post("/global/backfill-news", status_code=202)
async def backfill_supply_chain_news_endpoint(days: int = 14):
    """回填近期资讯与供应链合作方的关联。"""
    from app.tasks.supply_chain_tasks import backfill_supply_chain_news_links

    backfill_supply_chain_news_links.delay(days)
    return {"message": f"近 {days} 天供应链资讯关联回填任务已提交"}
