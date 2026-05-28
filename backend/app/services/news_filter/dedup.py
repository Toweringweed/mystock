"""跨源近似去重（SimHash）

SHA256 content_hash 已处理"完全相同"去重。SimHash 用于"近似相同"——
同一新闻被多家媒体转载、改个标题、调换语序的情况。

策略：
1. 标题归一化（去标点/全角半角统一/去空白）
2. 计算 64 位 SimHash 指纹
3. 与近 24h 内已入库的指纹比较，汉明距离 ≤ THRESHOLD 视为重复
"""
import logging
import re
import unicodedata
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import IndustryNews

logger = logging.getLogger(__name__)

HAMMING_THRESHOLD = 3  # 汉明距离阈值
DEDUP_WINDOW_HOURS = 24  # 只与近 24h 比较

_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def normalize_title(title: str) -> str:
    """标题归一化：全角→半角、去标点、转小写、去空白"""
    if not title:
        return ""
    norm = unicodedata.normalize("NFKC", title)
    norm = _PUNCT_RE.sub("", norm)
    return norm.lower()


def compute_simhash(title: str) -> int | None:
    """计算 64 位 SimHash 指纹。返回有符号 64 位整数（PostgreSQL BIGINT）"""
    norm = normalize_title(title)
    if not norm or len(norm) < 4:
        return None
    try:
        from simhash import Simhash
    except ImportError:
        logger.warning("simhash 未安装，跳过 SimHash 计算")
        return None

    # 按字符 2-gram 切分（中文友好）
    features = [norm[i : i + 2] for i in range(len(norm) - 1)] or [norm]
    sh = Simhash(features, f=64)
    val = sh.value
    # 转有符号 BIGINT
    if val >= (1 << 63):
        val -= 1 << 64
    return val


def hamming_distance(a: int, b: int) -> int:
    """两个 64 位 SimHash 的汉明距离"""
    # 转回无符号比较
    ua = a & ((1 << 64) - 1)
    ub = b & ((1 << 64) - 1)
    return bin(ua ^ ub).count("1")


async def find_duplicate(
    db: AsyncSession, simhash: int, exclude_id: int | None = None
) -> int | None:
    """在近 24h 内(以 crawled_at 为准)查找近似重复的资讯,返回重复项的 news_id 或 None。

    注:cutoff 用 crawled_at 而非 published_at,避免老新闻被新爬入时漏掉与最近相似新闻的比对。
    """
    if simhash is None:
        return None
    cutoff = datetime.now() - timedelta(hours=DEDUP_WINDOW_HOURS)

    stmt = select(IndustryNews.id, IndustryNews.simhash).where(
        IndustryNews.simhash.is_not(None),
        IndustryNews.crawled_at >= cutoff,
    )
    if exclude_id is not None:
        stmt = stmt.where(IndustryNews.id != exclude_id)

    result = await db.execute(stmt)
    for row_id, row_hash in result.all():
        if row_hash is None:
            continue
        if hamming_distance(simhash, row_hash) <= HAMMING_THRESHOLD:
            return row_id
    return None
