"""关键词库构建器

从 stocks / stock_aliases / supply_chains 三个来源派生每只自选股的匹配关键词，
缓存到 Redis（key=news:keywords，TTL 1h）。
"""
import json
import logging
import re
from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.stock_alias import StockAlias
from app.models.supply_chain import SupplyChain

logger = logging.getLogger(__name__)

CACHE_KEY = "news:keywords"
CACHE_TTL_SEC = 3600

# 公司名后缀，去掉以提取短名
COMPANY_SUFFIXES = [
    "股份有限公司", "有限公司", "集团股份有限公司", "控股集团有限公司",
    "控股有限公司", "股份", "集团", "控股", "公司", "(集团)", "（集团）",
]

# 至少 2 个字符的短名才有意义
MIN_ALIAS_LEN = 2


@dataclass
class KeywordEntry:
    """一条匹配关键词"""
    keyword: str
    weight: float  # 命中权重（0~1）
    source_type: str  # code / name / short_name / alias / supply_chain


def derive_short_name(full_name: str) -> str | None:
    """从公司全名派生短名（例：'中国平安保险(集团)股份有限公司' -> '中国平安保险'）"""
    if not full_name:
        return None
    name = full_name.strip()
    # 按长度倒序剥离后缀（先剥长的，避免 '股份' 把 '股份有限公司' 截断）
    for suffix in sorted(COMPANY_SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    name = re.sub(r"[\(\（].*?[\)\）]$", "", name).strip()
    if len(name) < MIN_ALIAS_LEN or name == full_name:
        return None
    return name


def normalize_code_variants(code: str, market: str) -> list[str]:
    """A股代码不变；港股代码同时返回带前导 0 与不带前导 0 两种形式"""
    variants = [code]
    if market == "HK" and code.isdigit():
        stripped = code.lstrip("0") or "0"
        if stripped != code:
            variants.append(stripped)
    return variants


async def build_keywords(db: AsyncSession) -> dict[int, list[KeywordEntry]]:
    """构建每只自选股的关键词字典 {stock_id -> [KeywordEntry]}"""
    result = await db.execute(select(Stock).where(Stock.is_watchlist.is_(True)))
    stocks: list[Stock] = list(result.scalars().all())
    if not stocks:
        return {}

    stock_ids = [s.id for s in stocks]

    # 加载 aliases
    alias_rows = await db.execute(
        select(StockAlias).where(StockAlias.stock_id.in_(stock_ids))
    )
    alias_map: dict[int, list[StockAlias]] = {}
    for a in alias_rows.scalars().all():
        alias_map.setdefault(a.stock_id, []).append(a)

    # 加载 supply_chain（公司名作为关联关键词，权重 0.5）
    sc_rows = await db.execute(
        select(SupplyChain).where(SupplyChain.stock_id.in_(stock_ids))
    )
    sc_map: dict[int, list[SupplyChain]] = {}
    for sc in sc_rows.scalars().all():
        sc_map.setdefault(sc.stock_id, []).append(sc)

    out: dict[int, list[KeywordEntry]] = {}
    for s in stocks:
        entries: list[KeywordEntry] = []
        seen: set[str] = set()

        def add(kw: str | None, weight: float, source_type: str) -> None:
            if not kw or len(kw) < 1:
                return
            kw_clean = kw.strip()
            if not kw_clean or kw_clean in seen:
                return
            seen.add(kw_clean)
            entries.append(
                KeywordEntry(keyword=kw_clean, weight=weight, source_type=source_type)
            )

        # 1. 代码（含港股两种形式）
        for variant in normalize_code_variants(s.code, s.market):
            add(variant, 1.0, "code")

        # 2. 全称
        add(s.name, 1.0, "name")

        # 3. 短名（自动派生）
        short = derive_short_name(s.name)
        if short:
            add(short, 0.8, "short_name")

        # 4. 用户/AI 维护的别名
        for a in alias_map.get(s.id, []):
            add(a.alias, a.weight, f"alias:{a.alias_type}")

        # 5. 供应链上下游公司名（关联关键词，权重 0.5）
        for sc in sc_map.get(s.id, []):
            add(sc.company_name, 0.5, f"supply_chain:{sc.relation_type}")

        if entries:
            out[s.id] = entries

    logger.info(f"[keyword_builder] 构建关键词库：{len(out)} 只自选股，"
                f"共 {sum(len(v) for v in out.values())} 条关键词")
    return out


async def get_keywords_cached(db: AsyncSession) -> dict[int, list[KeywordEntry]]:
    """优先从 Redis 取，缓存未命中则重建"""
    try:
        from redis.asyncio import Redis

        from app.core.config import settings as app_settings

        redis = Redis.from_url(app_settings.redis_url, decode_responses=True)
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                raw = json.loads(cached)
                return {
                    int(sid): [KeywordEntry(**e) for e in entries]
                    for sid, entries in raw.items()
                }
        finally:
            await redis.aclose()
    except Exception as e:
        logger.debug(f"[keyword_builder] Redis 缓存读取失败，回退到 DB: {e}")

    keywords = await build_keywords(db)
    await _save_cache(keywords)
    return keywords


async def _save_cache(keywords: dict[int, list[KeywordEntry]]) -> None:
    try:
        from redis.asyncio import Redis

        from app.core.config import settings as app_settings

        redis = Redis.from_url(app_settings.redis_url, decode_responses=True)
        try:
            payload = {
                str(sid): [asdict(e) for e in entries]
                for sid, entries in keywords.items()
            }
            await redis.setex(CACHE_KEY, CACHE_TTL_SEC, json.dumps(payload))
        finally:
            await redis.aclose()
    except Exception as e:
        logger.debug(f"[keyword_builder] Redis 缓存写入失败: {e}")


async def invalidate_cache() -> None:
    """自选股变更时调用"""
    try:
        from redis.asyncio import Redis

        from app.core.config import settings as app_settings

        redis = Redis.from_url(app_settings.redis_url, decode_responses=True)
        try:
            await redis.delete(CACHE_KEY)
        finally:
            await redis.aclose()
    except Exception:
        pass
