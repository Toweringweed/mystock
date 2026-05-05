"""URGENT_NEWS 事件登记

资讯流水线已经在 process_pending_news 即时推送过 urgent 资讯；这里把它登记到
stock_events 表，是为了让 daily_summary 的"近 7 天事件"上下文与 MCP 视图能统一感知。
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import IndustryNews, NewsStockRelation
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)

# 跑漏一天时仍可补登记的回看窗口
LOOKBACK_DAYS = 2


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    target = target_date or date.today()
    cutoff = datetime.combine(
        target - timedelta(days=LOOKBACK_DAYS),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )

    rows = await db.execute(
        select(IndustryNews, NewsStockRelation.stock_id, NewsStockRelation.relevance)
        .join(NewsStockRelation, NewsStockRelation.news_id == IndustryNews.id)
        .where(IndustryNews.urgency == "urgent")
        .where(IndustryNews.processed_at.is_not(None))
        .where(IndustryNews.processed_at >= cutoff)
    )
    created = 0
    for news, stock_id, relevance in rows.all():
        ok = await upsert_event(
            db,
            stock_id=stock_id,
            event_type="URGENT_NEWS",
            severity="high",
            dedup_key=str(news.id),  # 一条 urgent 资讯对每只相关股各登记一次
            title=f"[urgent] {news.title[:140]}",
            payload={
                "news_id": news.id,
                "source": news.source,
                "direction": news.direction,
                "importance_score": news.importance_score,
                "relevance": float(relevance) if relevance else None,
                "summary": news.summary,
                "source_url": news.source_url,
            },
            triggered_at=news.published_at or news.processed_at,
        )
        if ok:
            created += 1
    return created
