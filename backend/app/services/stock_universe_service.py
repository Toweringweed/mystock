"""股票全量列表本地缓存服务

从 AKShare 拉取全量 A股 + 港股 基础信息写入 stock_universe 表，
后续搜索直接查本地库，避免每次联网导致的 1 分钟等待。
"""
import asyncio
import logging

from sqlalchemy import delete, func, select, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_universe import StockUniverse

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 搜索（毫秒级，查本地 DB）
# ──────────────────────────────────────────────

async def search_universe(db: AsyncSession, keyword: str, limit: int = 20) -> list[dict]:
    """在本地 stock_universe 表中搜索，按代码精确匹配优先排序"""
    kw = keyword.strip()
    stmt = (
        select(StockUniverse)
        .where(
            or_(
                StockUniverse.code.ilike(f"%{kw}%"),
                StockUniverse.name.ilike(f"%{kw}%"),
            )
        )
        .order_by(
            # 代码完全匹配排最前
            (StockUniverse.code == kw).desc(),
            # 代码前缀匹配次之
            StockUniverse.code.ilike(f"{kw}%").desc(),
            StockUniverse.code,
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "code": r.code,
            "name": r.name,
            "market": r.market,
            "industry": r.industry,
        }
        for r in rows
    ]


async def get_universe_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(StockUniverse))
    return result.scalar_one()


# ──────────────────────────────────────────────
# 同步（写入全量数据）
# ──────────────────────────────────────────────

async def sync_stock_universe(db: AsyncSession) -> dict:
    """从 AKShare 拉取全量 A股 + 港股 列表，upsert 到 stock_universe 表"""
    a_rows = await asyncio.to_thread(_fetch_a_stock_list)
    logger.info(f"[Universe] A股 {len(a_rows)} 条")

    await asyncio.sleep(0.5)  # AKShare 限速

    hk_rows = await asyncio.to_thread(_fetch_hk_stock_list)
    logger.info(f"[Universe] 港股 {len(hk_rows)} 条")

    all_rows = a_rows + hk_rows
    if not all_rows:
        logger.warning("[Universe] 未获取到任何数据，跳过写入")
        return {"a_count": 0, "hk_count": 0}

    # upsert（code 是主键，冲突时更新 name/industry/updated_at）
    stmt = pg_insert(StockUniverse).values(all_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "industry": stmt.excluded.industry,
            "updated_at": func.now(),
        },
    )
    await db.execute(stmt)
    await db.commit()

    logger.info(f"[Universe] 同步完成，共 {len(all_rows)} 条")
    return {"a_count": len(a_rows), "hk_count": len(hk_rows)}


def _fetch_a_stock_list() -> list[dict]:
    """同步获取全量 A股 列表（在线程池中执行）"""
    import akshare as ak
    try:
        df = ak.stock_info_a_code_name()
        return [
            {"code": row["code"], "name": row["name"], "market": "A", "industry": None}
            for _, row in df.iterrows()
        ]
    except Exception as e:
        logger.error(f"[Universe] A股列表获取失败: {e}")
        return []


def _fetch_hk_stock_list() -> list[dict]:
    """同步获取全量港股列表（在线程池中执行）"""
    import akshare as ak
    try:
        df = ak.stock_hk_spot_em()
        return [
            {
                "code": row["代码"].zfill(5),
                "name": row["名称"],
                "market": "HK",
                "industry": None,
            }
            for _, row in df.iterrows()
        ]
    except Exception as e:
        logger.error(f"[Universe] 港股列表获取失败: {e}")
        return []
