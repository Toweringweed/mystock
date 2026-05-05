"""券商研报爬虫（东财研报中心，免登录元数据）

抓取个股研报列表，返回结构含两层：
- 主信息：标题 / source_url(PDF) / published_at / source / category="research"
- _meta：评级 / 机构 / 三年 EPS·PE 预测，写入 research_report_meta 扩展表
"""
import logging
from datetime import datetime, time

from app.services.data_fetcher.research_report_fetcher import fetch_research_reports
from app.services.news_crawler.base_crawler import BaseCrawler

logger = logging.getLogger(__name__)


class ResearchCrawler(BaseCrawler):
    source_name = "research_em"
    category = "research"

    async def fetch_by_code(
        self, code: str, days: int = 30, limit: int = 20
    ) -> list[dict]:
        """单只股票最近 days 天的研报，最多 limit 条"""
        try:
            items = await fetch_research_reports(code, days=days, max_items=limit)
        except Exception as e:
            logger.error(f"[research_em][{code}] 研报抓取失败: {e}")
            return []

        results: list[dict] = []
        for it in items:
            title = f"{it['broker']}：{it['title']}"
            published_at = (
                datetime.combine(it["published_at"], time(0, 0))
                if it.get("published_at") else None
            )
            base = self._normalize(
                title=title,
                content="",
                url=it.get("pdf_url") or "",
                published_at=published_at,
            )
            # 把评级 / 预测一起带出来给 saver 使用
            base["_meta"] = {
                "broker": it["broker"],
                "rating": it.get("rating"),
                "forecast_year_base": it.get("forecast_year_base"),
                "eps_y1": it.get("eps_y1"),
                "eps_y2": it.get("eps_y2"),
                "eps_y3": it.get("eps_y3"),
                "pe_y1": it.get("pe_y1"),
                "pe_y2": it.get("pe_y2"),
                "pe_y3": it.get("pe_y3"),
                "pdf_url": it.get("pdf_url"),
                "_dedup_key": f"research:{code}:{it['broker']}:{it['title']}:{it['published_at']}",
            }
            results.append(base)
        return results

    async def fetch_latest(self) -> list[dict]:
        """BaseCrawler 接口要求；研报按 stock 维度抓，不在这里实现"""
        return []
