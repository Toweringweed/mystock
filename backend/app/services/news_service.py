"""资讯存取服务"""
import hashlib
import logging

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import IndustryNews, NewsStockRelation
from app.models.stock import Stock

logger = logging.getLogger(__name__)


def _hash_content(title: str, source: str) -> str:
    return hashlib.sha256(f"{source}:{title}".encode()).hexdigest()


async def save_news_batch(db: AsyncSession, articles: list[dict]) -> int:
    """批量写入资讯，ON CONFLICT DO NOTHING（去重）"""
    if not articles:
        return 0

    rows = []
    for a in articles:
        h = _hash_content(a.get("title", ""), a.get("source", ""))
        rows.append({
            "title": a.get("title", ""),
            "content": a.get("content"),
            "summary": a.get("summary"),
            "source": a.get("source", ""),
            "source_url": a.get("source_url"),
            "published_at": a.get("published_at"),
            "sentiment": a.get("sentiment"),
            "related_industries": a.get("related_industries", []),
            "content_hash": h,
            "category": a.get("category"),
            "source_authority": a.get("source_authority"),
        })

    stmt = insert(IndustryNews).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["content_hash"])
    result = await db.execute(stmt)
    await db.flush()
    return result.rowcount


def _normalize_title(title: str) -> str:
    """归一化标题用于跨源去重（去除空白、标点差异）"""
    import re
    return re.sub(r"\s+", "", title or "").strip().lower()


def _dedupe_by_title(items: list[IndustryNews], limit: int) -> list[IndustryNews]:
    """按标题去重，保留每个标题第一次出现的记录（已按时间倒序，故为最新一条）"""
    seen: set[str] = set()
    out: list[IndustryNews] = []
    for it in items:
        key = _normalize_title(it.title)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out


async def get_news_feed(
    db: AsyncSession,
    codes: list[str],
    limit: int = 50,
    urgency: str | None = None,
    min_score: float | None = None,
) -> list[IndustryNews]:
    # 多取一些以便去重后仍达到 limit
    fetch_limit = limit * 3
    if not codes:
        stmt = select(IndustryNews).order_by(IndustryNews.published_at.desc())
        if urgency:
            stmt = stmt.where(IndustryNews.urgency == urgency)
        if min_score is not None:
            stmt = stmt.where(IndustryNews.importance_score >= min_score)
        stmt = stmt.limit(fetch_limit)
        result = await db.execute(stmt)
        return _dedupe_by_title(list(result.scalars().all()), limit)

    # 按股票关联筛选
    stock_ids_result = await db.execute(
        select(Stock.id).where(Stock.code.in_(codes))
    )
    stock_ids = list(stock_ids_result.scalars().all())
    if not stock_ids:
        return []

    stmt = (
        select(IndustryNews)
        .join(NewsStockRelation, NewsStockRelation.news_id == IndustryNews.id)
        .where(NewsStockRelation.stock_id.in_(stock_ids))
        .order_by(IndustryNews.published_at.desc())
    )
    if urgency:
        stmt = stmt.where(IndustryNews.urgency == urgency)
    if min_score is not None:
        stmt = stmt.where(IndustryNews.importance_score >= min_score)
    stmt = stmt.limit(fetch_limit)
    result = await db.execute(stmt)
    return _dedupe_by_title(list(result.scalars().all()), limit)


async def get_stock_news(
    db: AsyncSession,
    code: str,
    limit: int = 20,
    urgency: str | None = None,
    min_score: float | None = None,
) -> list[IndustryNews]:
    return await get_news_feed(db, [code], limit, urgency=urgency, min_score=min_score)


async def delete_news(db: AsyncSession, news_id: int) -> bool:
    """删除一条资讯（同时级联删除关联记录）"""
    await db.execute(
        delete(NewsStockRelation).where(NewsStockRelation.news_id == news_id)
    )
    result = await db.execute(
        delete(IndustryNews).where(IndustryNews.id == news_id)
    )
    await db.commit()
    return result.rowcount > 0
