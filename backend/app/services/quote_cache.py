"""实时行情 Redis 缓存层"""
import json
import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None

QUOTE_TTL = 60  # 行情缓存 60 秒
QUOTE_KEY_PREFIX = "quote:"


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def update_quote_cache(quotes: list[dict]) -> None:
    """批量写入实时行情到 Redis"""
    r = get_redis()
    pipe = r.pipeline()
    for q in quotes:
        key = f"{QUOTE_KEY_PREFIX}{q['code']}"
        pipe.setex(key, QUOTE_TTL, json.dumps(q))
    await pipe.execute()


async def get_quote(code: str) -> dict | None:
    """从缓存读取单只股票行情"""
    r = get_redis()
    raw = await r.get(f"{QUOTE_KEY_PREFIX}{code}")
    if raw:
        return json.loads(raw)
    return None


async def get_quotes(codes: list[str]) -> dict[str, dict]:
    """批量从缓存读取行情，返回 {code: quote}"""
    r = get_redis()
    keys = [f"{QUOTE_KEY_PREFIX}{code}" for code in codes]
    values = await r.mget(*keys)
    result = {}
    for code, raw in zip(codes, values):
        if raw:
            result[code] = json.loads(raw)
    return result
