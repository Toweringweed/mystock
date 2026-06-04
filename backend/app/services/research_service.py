"""券商研报查询服务"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import IndustryNews
from app.models.research import ResearchReportMeta
from app.models.stock import Stock
from app.schemas.research import GlobalResearchReportRead, ResearchReportRead

_PLACEHOLDER_PREFIX = "["  # "[PDF 下载失败]" 等占位
_PLACEHOLDER_MAX_LEN = 60


def _is_real_content(content: str | None) -> bool:
    if content is None:
        return False
    if (
        len(content) <= _PLACEHOLDER_MAX_LEN
        and content.startswith(_PLACEHOLDER_PREFIX)
        and content.endswith("]")
    ):
        return False
    return True


def _meta_to_read(
    meta: ResearchReportMeta,
    title: str,
    published_at: datetime | None,
    summary: str | None = None,
    content: str | None = None,
) -> ResearchReportRead:
    target_price = None
    eps_y1 = float(meta.eps_y1) if meta.eps_y1 is not None else None
    pe_y1 = float(meta.pe_y1) if meta.pe_y1 is not None else None

    # manual-add stores explicit target prices as a fake EPS/PE pair:
    # eps_y1 = target_price, pe_y1 = 1.0. Expose it as target_price so the
    # research table does not mislabel the target as EPS.
    if eps_y1 is not None and pe_y1 is not None and pe_y1 <= 1.5:
        target_price = eps_y1
        eps_y1 = None
        pe_y1 = None

    return ResearchReportRead(
        news_id=meta.news_id,
        title=title,
        broker=meta.broker,
        rating=meta.rating,
        published_at=published_at,
        pdf_url=meta.pdf_url,
        forecast_year_base=meta.forecast_year_base,
        target_price=target_price,
        eps_y1=eps_y1,
        eps_y2=float(meta.eps_y2) if meta.eps_y2 is not None else None,
        eps_y3=float(meta.eps_y3) if meta.eps_y3 is not None else None,
        pe_y1=pe_y1,
        pe_y2=float(meta.pe_y2) if meta.pe_y2 is not None else None,
        pe_y3=float(meta.pe_y3) if meta.pe_y3 is not None else None,
        summary=summary,
        content_ready=_is_real_content(content),
    )


async def list_for_stock(
    db: AsyncSession, code: str, limit: int = 20
) -> list[ResearchReportRead]:
    """按发布日期 desc 列出某股最近的研报"""
    stock_id_res = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = stock_id_res.scalar_one_or_none()
    if stock_id is None:
        return []

    res = await db.execute(
        select(
            ResearchReportMeta,
            IndustryNews.title,
            IndustryNews.published_at,
            IndustryNews.summary,
            IndustryNews.content,
        )
        .join(IndustryNews, IndustryNews.id == ResearchReportMeta.news_id)
        .where(ResearchReportMeta.stock_id == stock_id)
        .order_by(IndustryNews.published_at.desc().nullslast())
        .limit(limit)
    )
    return [
        _meta_to_read(meta, title, pub, summary, content)
        for meta, title, pub, summary, content in res.all()
    ]


async def list_global(
    db: AsyncSession,
    *,
    code: str | None = None,
    broker: str | None = None,
    rating: str | None = None,
    days: int = 30,
    limit: int = 100,
) -> list[GlobalResearchReportRead]:
    """全局研报库（按筛选条件）"""
    cutoff = datetime.now() - timedelta(days=days)

    stmt = (
        select(
            ResearchReportMeta,
            IndustryNews.title,
            IndustryNews.published_at,
            IndustryNews.summary,
            IndustryNews.content,
            Stock.code,
            Stock.name,
        )
        .join(IndustryNews, IndustryNews.id == ResearchReportMeta.news_id)
        .join(Stock, Stock.id == ResearchReportMeta.stock_id)
        .where(IndustryNews.published_at >= cutoff)
    )

    if code:
        stmt = stmt.where(Stock.code == code)
    if broker:
        stmt = stmt.where(ResearchReportMeta.broker == broker)
    if rating:
        stmt = stmt.where(ResearchReportMeta.rating == rating)

    stmt = stmt.order_by(IndustryNews.published_at.desc().nullslast()).limit(limit)
    res = await db.execute(stmt)

    out: list[GlobalResearchReportRead] = []
    for meta, title, pub, summary, content, scode, sname in res.all():
        base = _meta_to_read(meta, title, pub, summary, content)
        out.append(
            GlobalResearchReportRead(
                **base.model_dump(),
                code=scode,
                stock_name=sname,
            )
        )
    return out


async def list_brokers(db: AsyncSession, days: int = 90) -> list[str]:
    """近 N 天出现过的机构清单（用于筛选下拉）"""
    cutoff = datetime.now() - timedelta(days=days)
    res = await db.execute(
        select(ResearchReportMeta.broker)
        .join(IndustryNews, IndustryNews.id == ResearchReportMeta.news_id)
        .where(IndustryNews.published_at >= cutoff)
        .distinct()
        .order_by(ResearchReportMeta.broker)
    )
    return [b for (b,) in res.all() if b]
