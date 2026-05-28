"""巨潮资讯网公告爬虫(P0 资讯升级)— 仅深市精确直连

接口:POST https://www.cninfo.com.cn/new/hisAnnouncement/query
- stock 参数必须为 "证券代码,orgId" 格式,orgId 从 szse_stock.json 加载
- 沪市的 sse_stock.json 已不可用,沪市/北交所股票请使用 AKShare disclosure_em 兜底
- 比 AKShare 更实时(~分钟级 vs 半小时级)
- per-code Redis cursor(announcementId 单调递增)避免重复拉取

调用方:news_tasks.crawl_cninfo_disclosures (Tier-A 5min)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings as app_settings
from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
_SZSE_META_URL = "https://www.cninfo.com.cn/new/data/szse_stock.json"
_PDF_PREFIX = "https://static.cninfo.com.cn/"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_REDIS_CURSOR_KEY = "cninfo:cursor:{code}"
_REDIS_ORG_MAP_KEY = "cninfo:orgmap:szse"
_CURSOR_TTL_SEC = 60 * 60 * 24 * 7
_ORG_MAP_TTL_SEC = 60 * 60 * 24 * 7

_CST = timezone(timedelta(hours=8))


class CninfoCrawler(BaseCrawler):
    source_name = "cninfo"
    category = "announcement"

    def __init__(self) -> None:
        self._org_map: dict[str, str] | None = None  # code -> orgId

    @staticmethod
    def supports(code: str) -> bool:
        """仅深市(0/2/3 开头)"""
        return code.startswith(("0", "2", "3"))

    async def _load_org_map(self, client: httpx.AsyncClient) -> dict[str, str]:
        """加载深市 code -> orgId 映射,优先走 Redis 缓存"""
        if self._org_map:
            return self._org_map

        try:
            from redis.asyncio import Redis
            r = Redis.from_url(app_settings.redis_url, decode_responses=True)
            try:
                cached = await r.get(_REDIS_ORG_MAP_KEY)
                if cached:
                    self._org_map = json.loads(cached)
                    return self._org_map
            finally:
                await r.aclose()
        except Exception as e:
            logger.debug(f"[cninfo] redis org_map miss: {e}")

        # 从 cninfo 拉
        try:
            resp = await client.get(
                _SZSE_META_URL,
                headers={"User-Agent": _UA, "Referer": "https://www.cninfo.com.cn/"},
            )
            resp.raise_for_status()
            payload = resp.json()
            stock_list = payload.get("stockList", [])
            mp = {s["code"]: s["orgId"] for s in stock_list if s.get("code") and s.get("orgId")}
        except Exception as e:
            logger.error(f"[cninfo] 加载 szse_stock.json 失败: {e}")
            return {}

        self._org_map = mp

        # 写缓存
        try:
            from redis.asyncio import Redis
            r = Redis.from_url(app_settings.redis_url, decode_responses=True)
            try:
                await r.set(_REDIS_ORG_MAP_KEY, json.dumps(mp), ex=_ORG_MAP_TTL_SEC)
            finally:
                await r.aclose()
        except Exception as e:
            logger.debug(f"[cninfo] redis org_map cache fail: {e}")

        logger.info(f"[cninfo] 加载深市 orgId 映射 {len(mp)} 条")
        return mp

    async def _get_cursor(self, code: str) -> int:
        try:
            from redis.asyncio import Redis
            r = Redis.from_url(app_settings.redis_url, decode_responses=True)
            try:
                v = await r.get(_REDIS_CURSOR_KEY.format(code=code))
                return int(v) if v else 0
            finally:
                await r.aclose()
        except Exception:
            return 0

    async def _set_cursor(self, code: str, value: int) -> None:
        try:
            from redis.asyncio import Redis
            r = Redis.from_url(app_settings.redis_url, decode_responses=True)
            try:
                await r.set(
                    _REDIS_CURSOR_KEY.format(code=code), str(value), ex=_CURSOR_TTL_SEC
                )
            finally:
                await r.aclose()
        except Exception as e:
            logger.debug(f"[cninfo] redis set cursor fail: {e}")

    async def _fetch_one(
        self,
        client: httpx.AsyncClient,
        code: str,
        org_id: str,
        since_days: int = 3,
    ) -> list[dict]:
        end = datetime.now(_CST).strftime("%Y-%m-%d")
        start = (datetime.now(_CST) - timedelta(days=since_days)).strftime("%Y-%m-%d")
        data = {
            "stock": f"{code},{org_id}",
            "tabName": "fulltext",
            "pageSize": "30",
            "pageNum": "1",
            "column": "szse",
            "isHLtitle": "true",
            "sortName": "time",
            "sortType": "desc",
            "seDate": f"{start}~{end}",
        }
        try:
            r = await client.post(
                _QUERY_URL,
                data=data,
                headers={
                    "User-Agent": _UA,
                    "Referer": "https://www.cninfo.com.cn/new/disclosure",
                    "Origin": "https://www.cninfo.com.cn",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            logger.warning(f"[cninfo][{code}] 请求失败: {e}")
            return []

        anns = payload.get("announcements") or []
        if not anns:
            return []

        cursor = await self._get_cursor(code)
        out: list[dict] = []
        max_id = cursor
        for ann in anns:
            try:
                ann_id = int(ann.get("announcementId") or 0)
            except (TypeError, ValueError):
                continue
            if ann_id <= cursor:
                continue
            if ann_id > max_id:
                max_id = ann_id

            title = (ann.get("announcementTitle") or "").strip()
            if not title:
                continue
            ts_ms = ann.get("announcementTime")
            try:
                published_at = (
                    datetime.fromtimestamp(int(ts_ms) / 1000, tz=_CST)
                    if ts_ms
                    else None
                )
            except (TypeError, ValueError):
                published_at = None
            adj = ann.get("adjunctUrl") or ""
            url = (_PDF_PREFIX + adj.lstrip("/")) if adj else ""

            out.append(
                self._normalize(
                    title=title,
                    content="",
                    url=url,
                    published_at=published_at,
                )
            )

        if max_id > cursor:
            await self._set_cursor(code, max_id)
        return out

    async def fetch_for_codes(
        self,
        codes: list[str],
        since_days: int = 3,
        concurrency: int = 4,
    ) -> dict[str, list[dict]]:
        """对每个深市代码并发抓取,返回 {code: [...]}。沪市/北交所代码会被自动过滤掉。"""
        codes_szse = [c for c in codes if self.supports(c)]
        if not codes_szse:
            return {}

        out: dict[str, list[dict]] = {}
        sem = asyncio.Semaphore(concurrency)

        async with httpx.AsyncClient(timeout=20, verify=False) as client:
            org_map = await self._load_org_map(client)
            if not org_map:
                return {}

            async def _one(c: str):
                async with sem:
                    org_id = org_map.get(c)
                    if not org_id:
                        out[c] = []
                        return
                    items = await self._fetch_one(
                        client, c, org_id, since_days=since_days
                    )
                    out[c] = items
                    await asyncio.sleep(0.15)

            await asyncio.gather(*(_one(c) for c in codes_szse))

        return out

    async def fetch_latest(self) -> list[dict]:
        return []
