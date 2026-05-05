"""股票标签服务：CRUD + 批量加载 + AI 提取后写入"""
import logging
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.tag import StockTag, Tag

logger = logging.getLogger(__name__)


VALID_CATEGORIES = {"theme", "industry_chain", "attribute"}


async def list_all_tags(db: AsyncSession) -> list[Tag]:
    res = await db.execute(select(Tag).order_by(Tag.category, Tag.name))
    return list(res.scalars().all())


async def get_tags_for_stock(db: AsyncSession, stock_id: int) -> list[tuple[Tag, StockTag]]:
    """返回 [(Tag, StockTag), ...]，便于上层附带 source/confidence"""
    res = await db.execute(
        select(Tag, StockTag)
        .join(StockTag, StockTag.tag_id == Tag.id)
        .where(StockTag.stock_id == stock_id)
        .order_by(Tag.category, Tag.name)
    )
    return [(row[0], row[1]) for row in res.all()]


async def get_tags_for_stocks(
    db: AsyncSession, stock_ids: list[int]
) -> dict[int, list[Tag]]:
    """批量加载，返回 {stock_id: [Tag, ...]}。给 watchlist table 用，避免 N+1"""
    if not stock_ids:
        return {}
    res = await db.execute(
        select(StockTag.stock_id, Tag)
        .join(Tag, Tag.id == StockTag.tag_id)
        .where(StockTag.stock_id.in_(stock_ids))
        .order_by(Tag.category, Tag.name)
    )
    out: dict[int, list[Tag]] = defaultdict(list)
    for stock_id, tag in res.all():
        out[stock_id].append(tag)
    return dict(out)


async def list_stocks_by_tag(db: AsyncSession, tag_id: int) -> list[Stock]:
    res = await db.execute(
        select(Stock)
        .join(StockTag, StockTag.stock_id == Stock.id)
        .where(StockTag.tag_id == tag_id)
        .where(Stock.is_watchlist.is_(True))
        .order_by(Stock.code)
    )
    return list(res.scalars().all())


async def _upsert_tag(
    db: AsyncSession, name: str, category: str, description: str | None = None
) -> Tag:
    """按 name 唯一键 upsert，返回 Tag 实例"""
    name = name.strip().lstrip("#").strip()
    if category not in VALID_CATEGORIES:
        category = "theme"
    res = await db.execute(select(Tag).where(Tag.name == name))
    tag = res.scalar_one_or_none()
    if tag:
        return tag
    tag = Tag(name=name, category=category, description=description)
    db.add(tag)
    await db.flush()
    return tag


async def attach_tag(
    db: AsyncSession,
    stock_id: int,
    name: str,
    category: str = "theme",
    source: str = "manual",
    confidence: float | None = None,
    description: str | None = None,
) -> Tag:
    """挂载标签：tag 不存在则创建；stock_tags 幂等（冲突即更新 source/confidence）"""
    tag = await _upsert_tag(db, name=name, category=category, description=description)
    stmt = (
        pg_insert(StockTag)
        .values(
            stock_id=stock_id,
            tag_id=tag.id,
            source=source,
            confidence=confidence,
        )
        .on_conflict_do_update(
            index_elements=[StockTag.stock_id, StockTag.tag_id],
            set_={"source": source, "confidence": confidence},
        )
    )
    await db.execute(stmt)
    await db.flush()
    return tag


async def detach_tag(db: AsyncSession, stock_id: int, tag_id: int) -> int:
    res = await db.execute(
        delete(StockTag).where(
            StockTag.stock_id == stock_id, StockTag.tag_id == tag_id
        )
    )
    return res.rowcount or 0


async def delete_tag_globally(db: AsyncSession, tag_id: int) -> tuple[int, int]:
    """全局删除某个标签 — 先解绑所有自选股,再删除标签本身。

    返回 (detached_links, deleted_tag) 计数。
    """
    detach_res = await db.execute(
        delete(StockTag).where(StockTag.tag_id == tag_id)
    )
    tag_res = await db.execute(delete(Tag).where(Tag.id == tag_id))
    return (detach_res.rowcount or 0, tag_res.rowcount or 0)


async def replace_ai_tags(
    db: AsyncSession,
    stock_id: int,
    tags: list[dict],
) -> list[Tag]:
    """删除该 stock 上 source=ai 的旧标签，全量重挂新的（不动 manual 标签）"""
    await db.execute(
        delete(StockTag).where(
            StockTag.stock_id == stock_id, StockTag.source == "ai"
        )
    )
    saved: list[Tag] = []
    for item in tags:
        name = (item.get("name") or "").strip().lstrip("#").strip()
        if not name:
            continue
        tag = await attach_tag(
            db,
            stock_id=stock_id,
            name=name,
            category=item.get("category", "theme"),
            source="ai",
            confidence=item.get("confidence"),
        )
        saved.append(tag)
    return saved


async def extract_and_save(db: AsyncSession, code: str) -> list[Tag]:
    """端到端：拉取股票特征 → 调 LLM → 写入"""
    from app.services.ai_analyzer.tags_extractor import TagsExtractor

    res = await db.execute(select(Stock).where(Stock.code == code))
    stock = res.scalar_one_or_none()
    if not stock:
        return []

    extractor = TagsExtractor()
    items = await extractor.extract(db=db, stock=stock)
    if not items:
        logger.warning(f"[{code}] AI 未提取到任何标签")
        return []

    saved = await replace_ai_tags(db, stock_id=stock.id, tags=items)
    logger.info(f"[{code}] 标签写入 {len(saved)} 条")
    return saved
