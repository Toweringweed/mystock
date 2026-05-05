"""股票标签 API"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.stock import Stock
from app.schemas.stock import StockRead
from app.schemas.tags import StockTagAttach, StockTagRead, TagRead
from app.services import tags_service

router = APIRouter()


# ─── 全量与反查 ──────────────────────────────────────────────────────────


@router.get("/tags", response_model=list[TagRead], tags=["tags"])
async def list_tags(db: AsyncSession = Depends(get_db)):
    """全部标签（用于筛选下拉）"""
    return await tags_service.list_all_tags(db)


@router.get("/tags/{tag_id}/stocks", response_model=list[StockRead], tags=["tags"])
async def list_stocks_by_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    """按标签反查自选股列表"""
    return await tags_service.list_stocks_by_tag(db, tag_id)


@router.delete(
    "/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["tags"],
)
async def delete_tag_global(tag_id: int, db: AsyncSession = Depends(get_db)):
    """全局删除标签 — 解绑所有股票后删除标签本身(不可恢复)"""
    detached, deleted = await tags_service.delete_tag_globally(db, tag_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"标签 {tag_id} 不存在")
    await db.commit()


# ─── 单只股票的标签 CRUD ─────────────────────────────────────────────────


async def _get_stock_id(db: AsyncSession, code: str) -> int:
    res = await db.execute(select(Stock.id).where(Stock.code == code))
    sid = res.scalar_one_or_none()
    if sid is None:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")
    return sid


@router.get(
    "/stocks/{code}/tags",
    response_model=list[StockTagRead],
    tags=["tags"],
)
async def get_stock_tags(code: str, db: AsyncSession = Depends(get_db)):
    """单只股票的标签列表（含 source / confidence）"""
    sid = await _get_stock_id(db, code)
    pairs = await tags_service.get_tags_for_stock(db, sid)
    return [
        StockTagRead(
            id=tag.id,
            name=tag.name,
            category=tag.category,
            description=tag.description,
            source=link.source,
            confidence=link.confidence,
        )
        for tag, link in pairs
    ]


@router.post(
    "/stocks/{code}/tags",
    response_model=TagRead,
    status_code=201,
    tags=["tags"],
)
async def add_stock_tag(
    code: str,
    payload: StockTagAttach,
    db: AsyncSession = Depends(get_db),
):
    """手动给股票添加标签（不存在则创建）"""
    sid = await _get_stock_id(db, code)
    tag = await tags_service.attach_tag(
        db,
        stock_id=sid,
        name=payload.name,
        category=payload.category,
        source="manual",
        description=payload.description,
    )
    await db.commit()
    return tag


@router.delete(
    "/stocks/{code}/tags/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["tags"],
)
async def remove_stock_tag(
    code: str, tag_id: int, db: AsyncSession = Depends(get_db)
):
    """从股票上移除某个标签"""
    sid = await _get_stock_id(db, code)
    await tags_service.detach_tag(db, sid, tag_id)
    await db.commit()


@router.post(
    "/stocks/{code}/tags/refresh",
    status_code=202,
    tags=["tags"],
)
async def refresh_stock_tags(code: str, db: AsyncSession = Depends(get_db)):
    """触发 AI 重新生成标签（异步）"""
    await _get_stock_id(db, code)  # 校验存在
    from app.tasks.tags_tasks import extract_tags_task
    extract_tags_task.delay(code)
    return {"message": "标签生成任务已提交"}
