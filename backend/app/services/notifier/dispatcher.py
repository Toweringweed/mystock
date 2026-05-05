"""分级推送调度器

负责把已打分的资讯按 urgency 路由到对应通道。

- urgent    : 立刻发送企业微信
- important : 写入 Redis SortedSet（按 published_at 排序），每整点聚合
- info      : 仅入库，每日 8:00 摘要
"""
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as app_settings
from app.models.news import IndustryNews, NewsStockRelation
from app.models.stock import Stock
from app.services.notifier import wechat_work_notifier
from app.services.settings_service import get_effective_value

logger = logging.getLogger(__name__)

REDIS_IMPORTANT_KEY = "notify:pending:important"
REDIS_EVENT_PENDING_KEY = "notify:pending:event"


async def _redis():
    from redis.asyncio import Redis
    return Redis.from_url(app_settings.redis_url, decode_responses=True)


def _bool_setting(value: str | None, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    return str(value).lower() in ("true", "1", "yes", "on")


async def _get_related_stocks(
    db: AsyncSession, news_id: int
) -> list[tuple[str, str]]:
    """返回 [(code, name)] 按 relevance 倒序"""
    result = await db.execute(
        select(Stock.code, Stock.name, NewsStockRelation.relevance)
        .join(NewsStockRelation, NewsStockRelation.stock_id == Stock.id)
        .where(NewsStockRelation.news_id == news_id)
        .order_by(NewsStockRelation.relevance.desc())
    )
    return [(code, name) for code, name, _ in result.all()]


async def dispatch_urgent(db: AsyncSession, news: IndustryNews) -> bool:
    """紧急级：立即推送"""
    enabled = _bool_setting(await get_effective_value(db, "notify_urgent_enabled"))
    if not enabled:
        return False
    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        logger.debug("[dispatcher] 未配置企业微信 webhook，跳过 urgent 推送")
        return False

    related = await _get_related_stocks(db, news.id)
    card = wechat_work_notifier.format_urgent_card(
        title=news.title,
        summary=news.summary or "",
        source=news.source,
        direction=news.direction or "neutral",
        importance_score=news.importance_score or 0.0,
        related_stocks=related,
        source_url=news.source_url,
    )
    return await wechat_work_notifier.send_markdown(webhook, card)


async def queue_important(news: IndustryNews, related_stocks: list[tuple[str, str]]) -> None:
    """重要级：写入 Redis SortedSet"""
    redis = await _redis()
    try:
        score = (news.published_at or datetime.now()).timestamp()
        payload = json.dumps({
            "news_id": news.id,
            "title": news.title,
            "summary": news.summary,
            "direction": news.direction,
            "stocks": [f"{name}({code})" for code, name in related_stocks],
            "ts": score,
        })
        await redis.zadd(REDIS_IMPORTANT_KEY, {payload: score})
    finally:
        await redis.aclose()


async def flush_important(db: AsyncSession) -> int:
    """整点任务：把 Redis SortedSet 中堆积的重要资讯一次性推送"""
    enabled = _bool_setting(await get_effective_value(db, "notify_important_enabled"))
    if not enabled:
        return 0
    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        return 0

    redis = await _redis()
    try:
        # 取所有，推送后清空
        raws = await redis.zrange(REDIS_IMPORTANT_KEY, 0, -1)
        if not raws:
            return 0
        items = []
        for raw in raws:
            try:
                items.append(json.loads(raw))
            except Exception:
                continue
        # 按时间倒序
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)
        card = wechat_work_notifier.format_important_summary(items[:50])
        ok = await wechat_work_notifier.send_markdown(webhook, card)
        if ok:
            await redis.delete(REDIS_IMPORTANT_KEY)
        return len(items)
    finally:
        await redis.aclose()


async def dispatch_event(db: AsyncSession, event) -> bool:
    """事件分级推送：high → 立即；medium → Redis 队列；low → 不推送

    `event` 接受 StockEvent ORM 对象或 event_id（int）。传 ORM 对象可避免一次重查。
    """
    from sqlalchemy import update
    from app.models.event import StockEvent
    from app.services.notifier.event_templates import format_event

    if isinstance(event, int):
        row = await db.execute(select(StockEvent).where(StockEvent.id == event))
        event = row.scalar_one_or_none()
    if not event or event.notified_at is not None:
        return False

    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        return False

    if event.severity == "high":
        urgent_enabled = _bool_setting(await get_effective_value(db, "notify_urgent_enabled"))
        if not urgent_enabled:
            return False
        card = format_event(
            event_type=event.event_type,
            severity=event.severity,
            title=event.title,
            payload=event.payload,
        )
        ok = await wechat_work_notifier.send_markdown(webhook, card)
        if ok:
            await db.execute(
                update(StockEvent)
                .where(StockEvent.id == event.id)
                .values(notified_at=datetime.now())
            )
        return ok

    if event.severity == "medium":
        important_enabled = _bool_setting(
            await get_effective_value(db, "notify_important_enabled")
        )
        if not important_enabled:
            return False
        redis = await _redis()
        try:
            score = (event.triggered_at or datetime.now()).timestamp()
            payload = json.dumps({
                "event_id": event.id,
                "event_type": event.event_type,
                "title": event.title,
            })
            await redis.zadd(REDIS_EVENT_PENDING_KEY, {payload: score})
        finally:
            await redis.aclose()
        return True

    return False


async def flush_event_queue(db: AsyncSession) -> int:
    """整点：把 Redis 中堆积的 medium 事件聚合推送"""
    from sqlalchemy import update
    from app.models.event import StockEvent
    from app.services.notifier.event_templates import format_aggregated

    enabled = _bool_setting(await get_effective_value(db, "notify_important_enabled"))
    if not enabled:
        return 0
    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        return 0

    # 企业微信 markdown 上限 4096 字；30 条以上分页，避免静默截断 + 队列无限堆积
    MAX_PER_CARD = 30
    redis = await _redis()
    try:
        raws = await redis.zrange(REDIS_EVENT_PENDING_KEY, 0, MAX_PER_CARD - 1)
        if not raws:
            return 0
        items: list[dict] = []
        event_ids: list[int] = []
        for raw in raws:
            try:
                d = json.loads(raw)
                items.append(d)
                event_ids.append(int(d["event_id"]))
            except Exception:
                continue
        card = format_aggregated(items)
        ok = await wechat_work_notifier.send_markdown(webhook, card)
        if ok:
            # 仅删除本批，剩余条目下一整点继续聚合
            await redis.zrem(REDIS_EVENT_PENDING_KEY, *raws)
            if event_ids:
                await db.execute(
                    update(StockEvent)
                    .where(StockEvent.id.in_(event_ids))
                    .values(notified_at=datetime.now())
                )
        return len(items)
    finally:
        await redis.aclose()


async def send_daily_summary(db: AsyncSession) -> int:
    """每日摘要：聚合昨日所有 info / important 级资讯"""
    enabled = _bool_setting(await get_effective_value(db, "notify_daily_summary_enabled"))
    if not enabled:
        return 0
    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        return 0

    cutoff = datetime.now() - timedelta(hours=24)
    result = await db.execute(
        select(IndustryNews)
        .where(
            IndustryNews.crawled_at >= cutoff,
            IndustryNews.processed_at.is_not(None),
            IndustryNews.urgency.in_(["important", "info"]),
        )
        .order_by(IndustryNews.importance_score.desc().nulls_last())
        .limit(30)
    )
    news_list = list(result.scalars().all())
    items = []
    for n in news_list:
        related = await _get_related_stocks(db, n.id)
        items.append({
            "title": n.title,
            "summary": n.summary,
            "direction": n.direction,
            "stocks": [f"{name}({code})" for code, name in related],
        })
    card = wechat_work_notifier.format_daily_summary(
        items, datetime.now().strftime("%Y-%m-%d")
    )
    ok = await wechat_work_notifier.send_markdown(webhook, card)
    return len(items) if ok else 0
