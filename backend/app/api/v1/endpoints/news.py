from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.news import NewsRead

router = APIRouter()


@router.get("/feed", response_model=list[NewsRead])
async def get_news_feed(
    codes: str = Query("", description="股票代码，逗号分隔，为空则返回所有"),
    limit: int = Query(50, ge=1, le=200),
    urgency: str | None = Query(None, description="urgent / important / info 过滤"),
    min_score: float | None = Query(None, ge=0.0, le=1.0, description="最低重要性分数"),
    db: AsyncSession = Depends(get_db),
):
    """获取资讯 Feed（按股票/紧急级/重要性过滤）"""
    from app.services.news_service import get_news_feed as _get
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    return await _get(db, code_list, limit, urgency=urgency, min_score=min_score)


@router.delete("/{news_id}", status_code=204)
async def delete_news(
    news_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除一条资讯"""
    from app.services.news_service import delete_news as _delete
    deleted = await _delete(db, news_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="资讯不存在")


@router.get("/{code}", response_model=list[NewsRead])
async def get_stock_news(
    code: str,
    limit: int = Query(20, ge=1, le=100),
    urgency: str | None = Query(None),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    """获取单只股票相关资讯"""
    from app.services.news_service import get_stock_news as _get
    return await _get(db, code, limit, urgency=urgency, min_score=min_score)
