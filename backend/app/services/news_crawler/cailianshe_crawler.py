"""财联社电报爬虫（via AKShare）"""
import asyncio
import logging
from datetime import datetime

from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class CailiansheCrawler(BaseCrawler):
    source_name = "cailianshe"

    async def fetch_latest(self, limit: int = 50) -> list[dict]:
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_news_em, symbol="")
            if df.empty:
                return []

            results = []
            for _, row in df.head(limit).iterrows():
                title = str(row.get("新闻标题", "") or row.get("title", ""))
                if not title:
                    continue
                content = str(row.get("新闻内容", "") or "")
                url = str(row.get("新闻链接", "") or "")
                # 尝试解析日期
                date_str = str(row.get("发布时间", "") or "")
                try:
                    published_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    published_at = None

                results.append(self._normalize(
                    title=title,
                    content=content,
                    url=url,
                    published_at=published_at,
                ))
            logger.info(f"[cailianshe] 抓取 {len(results)} 条")
            return results
        except Exception as e:
            logger.error(f"[cailianshe] 爬取失败: {e}")
            return []
