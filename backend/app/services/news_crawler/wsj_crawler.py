"""华尔街见闻爬虫"""
import logging
from datetime import UTC, datetime

import httpx

from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)

WSJ_LIVES_API = "https://api-one.wallstcn.com/apiv1/content/lives"


class WsjCrawler(BaseCrawler):
    source_name = "wsj_cn"

    async def fetch_latest(self, limit: int = 50) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    WSJ_LIVES_API,
                    params={"channel": "global-channel", "limit": limit},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                        "Referer": "https://wallstreetcn.com/",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            items = data.get("data", {}).get("items", [])
            results = []
            for item in items:
                content_data = item.get("content_data") or item
                title = content_data.get("title") or content_data.get("content", "")[:50]
                if not title:
                    continue

                ts = item.get("display_time") or item.get("created_at")
                published_at = datetime.fromtimestamp(ts, tz=UTC) if ts else None

                results.append(self._normalize(
                    title=title,
                    content=content_data.get("content", ""),
                    url=f"https://wallstreetcn.com/articles/{item.get('id', '')}",
                    published_at=published_at,
                ))
            logger.info(f"[wsj_cn] 抓取 {len(results)} 条")
            return results
        except Exception as e:
            logger.error(f"[wsj_cn] 爬取失败: {e}")
            return []
