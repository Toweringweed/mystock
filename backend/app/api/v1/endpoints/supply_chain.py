from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.supply_chain import GlobalSupplyChainResponse, SupplyChainRead

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


@router.get("/{code}", response_model=SupplyChainRead)
async def get_supply_chain(code: str, db: AsyncSession = Depends(get_db)):
    """获取单股供应链上下游数据"""
    from app.services.supply_chain_service import get_supply_chain as _get
    return await _get(db, code)


@router.post("/{code}/refresh", status_code=202)
async def refresh_supply_chain(code: str):
    """触发重新提取供应链（下载最新年报并 AI 解析）"""
    from app.tasks.supply_chain_tasks import extract_supply_chain_task
    extract_supply_chain_task.delay(code)
    return {"message": "供应链提取任务已提交"}
