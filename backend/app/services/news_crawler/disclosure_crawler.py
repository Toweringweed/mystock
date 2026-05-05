"""财报公告/业绩预告爬虫（东方财富 via AKShare）

抓取自选股的关键公告：业绩预告、业绩快报、季报、半年报、年报。
这些是时间节点最敏感的信息，应第一时间入库。
"""
import asyncio
import logging
from datetime import datetime

from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)

# 高优先级公告关键词
FINANCIAL_KEYWORDS = [
    "业绩预告", "业绩快报", "业绩说明", "年度报告", "年报",
    "半年报", "半年度报告", "季报", "一季报", "三季报",
    "季度报告", "定期报告", "财务报告",
]


class DisclosureCrawler(BaseCrawler):
    """个股财报公告爬虫"""
    source_name = "disclosure_em"
    category = "announcement"

    async def fetch_by_code(self, code: str, limit: int = 30) -> list[dict]:
        """抓取单只股票的关键财报公告"""
        try:
            import akshare as ak
            df = await asyncio.to_thread(
                ak.stock_individual_notice_report,
                security=code,
                symbol="全部",
            )
            if df is None or df.empty:
                return []

            # 只保留财报相关
            mask = df["公告标题"].str.contains("|".join(FINANCIAL_KEYWORDS), na=False)
            df = df[mask].head(limit)

            results = []
            for _, row in df.iterrows():
                title = str(row.get("公告标题", "")).strip()
                if not title:
                    continue
                date_str = str(row.get("公告日期", ""))
                try:
                    published_at = datetime.strptime(date_str, "%Y-%m-%d")
                except Exception:
                    published_at = None

                results.append(self._normalize(
                    title=title,
                    content="",
                    url=str(row.get("网址", "") or ""),
                    published_at=published_at,
                ))
            return results
        except Exception as e:
            logger.error(f"[disclosure_em][{code}] 公告抓取失败: {e}")
            return []

    async def fetch_latest(self) -> list[dict]:
        """BaseCrawler 要求实现，不单独使用"""
        return []
