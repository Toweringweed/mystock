"""财联社电报爬虫（via AKShare）"""
import asyncio
import logging
from datetime import date, datetime, time

from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class CailiansheCrawler(BaseCrawler):
    source_name = "cailianshe"

    async def fetch_latest(self, limit: int = 50) -> list[dict]:
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_info_global_cls, symbol="全部")
            if df.empty:
                return []

            results = []
            latest_rows = df.tail(limit).iloc[::-1]
            for _, row in latest_rows.iterrows():
                title = str(row.get("标题", "") or row.get("新闻标题", "") or row.get("title", "")).strip()
                if not title:
                    continue
                content = str(row.get("内容", "") or row.get("新闻内容", "") or "").strip()
                url = str(row.get("新闻链接", "") or row.get("url", "") or "").strip()
                published_at = self._parse_published_at(row)

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

    def _parse_published_at(self, row) -> datetime | None:
        published_at = row.get("发布时间")
        publish_date = row.get("发布日期")

        if isinstance(published_at, datetime):
            return published_at

        if publish_date is not None and published_at is not None:
            try:
                if not isinstance(publish_date, date):
                    publish_date = datetime.strptime(str(publish_date), "%Y-%m-%d").date()
                if not isinstance(published_at, time):
                    published_at = datetime.strptime(str(published_at), "%H:%M:%S").time()
                return datetime.combine(publish_date, published_at)
            except Exception:
                pass

        if published_at:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%H:%M:%S"):
                try:
                    parsed = datetime.strptime(str(published_at), fmt)
                    return parsed if fmt.startswith("%Y") else datetime.combine(datetime.now().date(), parsed.time())
                except Exception:
                    continue

        return None
