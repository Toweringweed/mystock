"""资讯爬虫基类"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


# 消息源权威度（0~1，用于规则打分）
SOURCE_AUTHORITY: dict[str, float] = {
    "disclosure_em": 1.0,
    "cninfo": 1.0,
    "research_em": 0.85,
    "wsj_cn": 0.7,
    "cailianshe": 0.7,
    "eastmoney": 0.5,
    "google_news": 0.5,
    "xueqiu": 0.3,
}


class BaseCrawler(ABC):
    source_name: str = "unknown"
    category: str = "news"  # announcement / news / social / research

    @abstractmethod
    async def fetch_latest(self) -> list[dict]:
        """抓取最新资讯，返回标准化列表"""
        ...

    def _normalize(
        self,
        title: str,
        content: str = "",
        url: str = "",
        published_at: datetime | None = None,
    ) -> dict:
        return {
            "title": title.strip(),
            "content": content.strip() or None,
            "summary": None,  # 由 AI 后处理填充
            "source": self.source_name,
            "source_url": url or None,
            "published_at": published_at or datetime.now(),
            "sentiment": None,
            "related_industries": [],
            "category": self.category,
            "source_authority": SOURCE_AUTHORITY.get(self.source_name, 0.5),
        }
