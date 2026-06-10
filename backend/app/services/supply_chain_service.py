"""供应链数据存取服务"""
import hashlib
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import StockEvent
from app.models.news import IndustryNews, NewsStockRelation
from app.models.stock import Stock
from app.models.supply_chain import (
    SupplyChain,
    SupplyChainCompany,
    SupplyChainCompanyAlias,
    SupplyChainNewsLink,
    SupplyChainRelationship,
)
from app.schemas.supply_chain import (
    GlobalSupplyChainResponse,
    SupplyChainCoverageItem,
    SupplyChainCoverageResponse,
    SupplyChainEdge,
    SupplyChainEventSummary,
    SupplyChainNode,
    SupplyChainRead,
    SupplyChainStockMeta,
)

logger = logging.getLogger(__name__)


def _normalize_company_name(name: str) -> str:
    import re

    return re.sub(r"[\s（）()《》\"'“”‘’·,，.。]+", "", name or "").lower()


def _text_contains_alias(text: str, alias: str) -> bool:
    if not text or not alias:
        return False
    if alias.isascii():
        import re

        return re.search(r"\b" + re.escape(alias) + r"\b", text, re.IGNORECASE) is not None
    return alias in text


async def _get_or_create_company(
    db: AsyncSession,
    *,
    name: str,
    stock_code: str | None = None,
    is_listed: bool = False,
    market: str | None = None,
    industry: str | None = None,
) -> int:
    normalized = _normalize_company_name(stock_code or name)
    display_name = (name or stock_code or "").strip()
    if not display_name:
        raise ValueError("company name is required")

    stmt = (
        pg_insert(SupplyChainCompany)
        .values(
            name=display_name[:100],
            normalized_name=normalized[:120],
            stock_code=stock_code,
            market=market,
            is_listed=is_listed,
            industry=industry,
        )
        .on_conflict_do_update(
            index_elements=["normalized_name"],
            set_={
                "name": display_name[:100],
                "stock_code": stock_code,
                "market": market,
                "is_listed": is_listed,
                "industry": industry,
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(SupplyChainCompany.id)
    )
    company_id = (await db.execute(stmt)).scalar_one()

    aliases = {display_name}
    if stock_code:
        aliases.add(stock_code)
    for alias in aliases:
        alias = alias.strip()
        if not alias:
            continue
        await db.execute(
            pg_insert(SupplyChainCompanyAlias)
            .values(
                company_id=company_id,
                alias=alias[:120],
                alias_type="code" if alias == stock_code else "name",
            )
            .on_conflict_do_nothing(index_elements=["company_id", "alias"])
        )
    return company_id


async def _sync_legacy_relationship(
    db: AsyncSession,
    *,
    stock_id: int,
    stock_code: str,
    stock_name: str,
    stock_market: str | None,
    legacy: SupplyChain,
) -> int | None:
    host_company_id = await _get_or_create_company(
        db,
        name=stock_name,
        stock_code=stock_code,
        is_listed=True,
        market=stock_market,
    )
    partner_company_id = await _get_or_create_company(
        db,
        name=legacy.company_name,
        stock_code=legacy.company_code,
        is_listed=bool(legacy.is_listed),
    )

    if legacy.relation_type == "upstream":
        source_company_id, target_company_id = partner_company_id, host_company_id
    elif legacy.relation_type == "downstream":
        source_company_id, target_company_id = host_company_id, partner_company_id
    else:
        source_company_id, target_company_id = host_company_id, partner_company_id

    stmt = (
        pg_insert(SupplyChainRelationship)
        .values(
            host_stock_id=stock_id,
            source_company_id=source_company_id,
            target_company_id=target_company_id,
            legacy_supply_chain_id=legacy.id,
            relation_type=legacy.relation_type,
            product_desc=legacy.product_desc,
            cooperation_desc=legacy.product_desc,
            percentage=legacy.percentage,
            importance=legacy.importance or "medium",
            confidence=0.55 if legacy.data_source == "ai_knowledge" else 0.7,
            data_source=legacy.data_source or "annual_report_ai",
        )
        .on_conflict_do_update(
            index_elements=[
                "host_stock_id",
                "source_company_id",
                "target_company_id",
                "relation_type",
                "product_desc",
            ],
            set_={
                "legacy_supply_chain_id": legacy.id,
                "cooperation_desc": legacy.product_desc,
                "percentage": legacy.percentage,
                "importance": legacy.importance or "medium",
                "updated_at": datetime.now(UTC),
            },
        )
        .returning(SupplyChainRelationship.id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _get_recent_supply_chain_events(
    db: AsyncSession,
    *,
    stock_ids: list[int] | None = None,
    days: int = 14,
    limit: int = 50,
) -> list[tuple[SupplyChainEventSummary, int | None, int]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            SupplyChainNewsLink,
            IndustryNews,
            Stock.code,
            Stock.name,
            SupplyChainCompany.name,
            SupplyChainCompany.stock_code,
        )
        .join(IndustryNews, IndustryNews.id == SupplyChainNewsLink.news_id)
        .join(Stock, Stock.id == SupplyChainNewsLink.stock_id)
        .join(SupplyChainCompany, SupplyChainCompany.id == SupplyChainNewsLink.company_id)
        .where(IndustryNews.published_at >= cutoff)
        .order_by(IndustryNews.published_at.desc(), SupplyChainNewsLink.id.desc())
        .limit(limit)
    )
    if stock_ids:
        stmt = stmt.where(SupplyChainNewsLink.stock_id.in_(stock_ids))

    rows = await db.execute(stmt)
    out: list[tuple[SupplyChainEventSummary, int | None, int]] = []
    for link, news, stock_code, stock_name, company_name, company_code in rows.all():
        out.append((
            SupplyChainEventSummary(
                news_id=news.id,
                stock_code=stock_code,
                stock_name=stock_name,
                company_name=company_name,
                company_code=company_code,
                title=news.title,
                published_at=news.published_at.isoformat() if news.published_at else None,
                urgency=news.urgency,
                importance_score=float(news.importance_score) if news.importance_score is not None else None,
                relevance=float(link.relevance),
                impact_direction=link.impact_direction,
                impact_summary=link.impact_summary,
            ),
            link.supply_chain_id,
            link.company_id,
        ))
    return out


async def get_supply_chain(db: AsyncSession, code: str) -> SupplyChainRead:
    result = await db.execute(
        select(Stock.id, Stock.name).where(Stock.code == code)
    )
    row = result.first()
    if not row:
        return SupplyChainRead(code=code, name=code)

    stock_id, name = row.id, row.name

    sc_result = await db.execute(
        select(SupplyChain)
        .where(SupplyChain.stock_id == stock_id)
        .order_by(SupplyChain.relation_type, SupplyChain.importance)
    )
    nodes = list(sc_result.scalars().all())

    event_rows = await _get_recent_supply_chain_events(db, stock_ids=[stock_id], days=14, limit=30)
    events_by_supply_chain: dict[int, list[SupplyChainEventSummary]] = defaultdict(list)
    for ev, supply_chain_id, _company_id in event_rows:
        if supply_chain_id:
            events_by_supply_chain[supply_chain_id].append(ev)

    def enrich_node(node: SupplyChain) -> SupplyChainNode:
        out = SupplyChainNode.model_validate(node)
        events = events_by_supply_chain.get(node.id, [])
        out.recent_event_count = len(events)
        out.urgent_event_count = sum(1 for e in events if e.urgency == "urgent")
        if events:
            out.latest_event_title = events[0].title
            out.latest_news_id = events[0].news_id
        return out

    upstream = [enrich_node(n) for n in nodes if n.relation_type == "upstream"]
    downstream = [enrich_node(n) for n in nodes if n.relation_type == "downstream"]
    competitors = [enrich_node(n) for n in nodes if n.relation_type == "competitor"]

    updated_at = nodes[0].updated_at.isoformat() if nodes else None

    return SupplyChainRead(
        code=code,
        name=name,
        upstream=upstream,
        downstream=downstream,
        competitors=competitors,
        updated_at=updated_at,
        recent_events=[ev for ev, _sid, _cid in event_rows],
    )


async def get_global_supply_chain(db: AsyncSession) -> GlobalSupplyChainResponse:
    """聚合所有自选股的上下游 → 全局供应链图(聚簇分组)。

    - 节点:自选股(主) + 上下游公司(外部)
    - 边:relation_type=upstream/downstream,from→to 始终代表"上游→下游"流向
    - 聚簇优先级:industry > theme tag > "未分组"(实际数据中 industry 普遍未填,主要靠 theme tag)
    """
    from app.models.tag import StockTag, Tag

    # 1) 全部自选股
    res = await db.execute(
        select(Stock.id, Stock.code, Stock.name, Stock.industry, Stock.market)
        .where(Stock.is_watchlist == True)  # noqa: E712
    )
    watchlist_rows = list(res.all())
    stock_id_to_code = {r.id: r.code for r in watchlist_rows}
    code_to_name = {r.code: (r.name or r.code) for r in watchlist_rows}
    {r.code: (r.market or "A") for r in watchlist_rows}

    watchlist_codes_set = set(stock_id_to_code.values())

    # 1b) 取每只自选股的 theme 标签(用于聚簇 fallback)
    tag_res = await db.execute(
        select(StockTag.stock_id, Tag.name)
        .join(Tag, Tag.id == StockTag.tag_id)
        .where(Tag.category == "theme")
        .where(StockTag.stock_id.in_([r.id for r in watchlist_rows] or [-1]))
    )
    stock_id_to_theme_tags: dict[int, list[str]] = defaultdict(list)
    for sid, tname in tag_res.all():
        stock_id_to_theme_tags[sid].append(tname)

    # 1c) 计算每个 theme tag 的覆盖度(决定 fallback 顺序)
    tag_popularity: dict[str, int] = defaultdict(int)
    for tags in stock_id_to_theme_tags.values():
        for t in tags:
            tag_popularity[t] += 1

    def cluster_key(stock_row) -> str:
        """聚簇 key:industry > 最热门 theme tag > '未分组'"""
        if stock_row.industry:
            return stock_row.industry
        tags = stock_id_to_theme_tags.get(stock_row.id, [])
        if tags:
            # 选股票自带的所有 theme tag 中覆盖度最高的(简化:覆盖度多的更可能是行业聚簇)
            return max(tags, key=lambda t: tag_popularity[t])
        return "未分组"

    code_to_cluster = {r.code: cluster_key(r) for r in watchlist_rows}

    # 2) 全部供应链关系
    sc_res = await db.execute(
        select(SupplyChain).where(SupplyChain.relation_type.in_(["upstream", "downstream"]))
    )
    all_sc = list(sc_res.scalars().all())
    recent_event_rows = await _get_recent_supply_chain_events(
        db,
        stock_ids=[r.id for r in watchlist_rows],
        days=14,
        limit=80,
    )
    recent_events = [ev for ev, _sid, _cid in recent_event_rows]
    events_by_supply_chain: dict[int, list[SupplyChainEventSummary]] = defaultdict(list)
    events_by_stock_code: dict[str, list[SupplyChainEventSummary]] = defaultdict(list)
    for ev, supply_chain_id, _company_id in recent_event_rows:
        events_by_stock_code[ev.stock_code].append(ev)
        if supply_chain_id:
            events_by_supply_chain[supply_chain_id].append(ev)

    # 3) 收集外部(非自选股)公司去重
    external: dict[str, SupplyChainStockMeta] = {}
    external_events: dict[str, list[SupplyChainEventSummary]] = defaultdict(list)
    edges: list[SupplyChainEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()  # 用 (from, to, product) 去重

    for sc in all_sc:
        host_code = stock_id_to_code.get(sc.stock_id)
        if not host_code:
            continue  # host 不是自选股,跳过

        partner_code = sc.company_code or f"_ext::{sc.company_name}"
        partner_name = sc.company_name

        # 外部公司去重收集
        if partner_code not in watchlist_codes_set:
            sc_events = events_by_supply_chain.get(sc.id, [])
            external_events[partner_code].extend(sc_events)
            if partner_code not in external:
                external[partner_code] = SupplyChainStockMeta(
                    code=partner_code,
                    name=partner_name,
                    industry=None,  # 外部公司行业未知
                    market="A" if sc.is_listed else "EXT",
                    recent_event_count=len(sc_events),
                    urgent_event_count=sum(1 for e in sc_events if e.urgency == "urgent"),
                    latest_event_title=sc_events[0].title if sc_events else None,
                    latest_news_id=sc_events[0].news_id if sc_events else None,
                )

        # 边:始终上游→下游
        if sc.relation_type == "upstream":
            from_code, to_code = partner_code, host_code
            from_name, to_name = partner_name, code_to_name.get(host_code, host_code)
        else:  # downstream
            from_code, to_code = host_code, partner_code
            from_name, to_name = code_to_name.get(host_code, host_code), partner_name

        edge_key = (from_code, to_code, sc.product_desc or "")
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        sc_events = events_by_supply_chain.get(sc.id, [])

        edges.append(SupplyChainEdge(
            from_code=from_code,
            to_code=to_code,
            from_name=from_name,
            to_name=to_name,
            product_desc=sc.product_desc,
            importance=sc.importance or "medium",
            relation_type=sc.relation_type,
            both_listed=(from_code in watchlist_codes_set and to_code in watchlist_codes_set),
            recent_event_count=len(sc_events),
            urgent_event_count=sum(1 for e in sc_events if e.urgency == "urgent"),
            latest_event_title=sc_events[0].title if sc_events else None,
            latest_news_id=sc_events[0].news_id if sc_events else None,
        ))

    # 4) 聚簇(仅自选股,外部公司不参与聚簇) — 用 cluster_key (industry > theme > 未分组)
    industry_groups: dict[str, list[str]] = defaultdict(list)
    for code, cluster in code_to_cluster.items():
        industry_groups[cluster].append(code)

    watchlist_metas = [
        SupplyChainStockMeta(
            code=r.code,
            name=r.name or r.code,
            industry=code_to_cluster.get(r.code, "未分组"),
            market=r.market or "A",
            recent_event_count=len(events_by_stock_code.get(r.code, [])),
            urgent_event_count=sum(1 for e in events_by_stock_code.get(r.code, []) if e.urgency == "urgent"),
            latest_event_title=events_by_stock_code.get(r.code, [None])[0].title
            if events_by_stock_code.get(r.code)
            else None,
            latest_news_id=events_by_stock_code.get(r.code, [None])[0].news_id
            if events_by_stock_code.get(r.code)
            else None,
        )
        for r in watchlist_rows
    ]

    external_metas = []
    for code, meta in external.items():
        events = external_events.get(code, [])
        if events:
            meta.recent_event_count = len(events)
            meta.urgent_event_count = sum(1 for e in events if e.urgency == "urgent")
            meta.latest_event_title = events[0].title
            meta.latest_news_id = events[0].news_id
        external_metas.append(meta)

    return GlobalSupplyChainResponse(
        watchlist_stocks=watchlist_metas,
        external_companies=external_metas,
        edges=edges,
        recent_events=recent_events,
        industry_groups=dict(industry_groups),
        stats={
            "watchlist_count": len(watchlist_metas),
            "external_count": len(external),
            "edge_count": len(edges),
            "industry_count": len(industry_groups),
            "cross_watchlist_edges": sum(1 for e in edges if e.both_listed),
            "highlighted_edges": sum(1 for e in edges if e.recent_event_count > 0),
            "recent_event_count": len(recent_events),
        },
    )


async def get_supply_chain_coverage(
    db: AsyncSession,
    *,
    min_upstream: int = 1,
    min_downstream: int = 1,
    min_competitors: int = 1,
) -> SupplyChainCoverageResponse:
    """审计自选股供应链覆盖率。

    完整覆盖的最低标准不是“有新闻”，而是至少有上游、下游、竞品三类基础关系。
    """
    rows = await db.execute(
        select(Stock.id, Stock.code, Stock.name)
        .where(Stock.is_watchlist.is_(True))
        .order_by(Stock.code)
    )
    stocks = list(rows.all())
    if not stocks:
        return SupplyChainCoverageResponse(
            items=[],
            stats={
                "watchlist_count": 0,
                "complete_count": 0,
                "partial_count": 0,
                "missing_count": 0,
                "gap_count": 0,
            },
        )

    counts_res = await db.execute(
        select(SupplyChain.stock_id, SupplyChain.relation_type, SupplyChain.id)
        .where(SupplyChain.stock_id.in_([s.id for s in stocks]))
    )
    counts: dict[int, dict[str, int]] = defaultdict(lambda: {
        "upstream": 0,
        "downstream": 0,
        "competitor": 0,
    })
    for stock_id, relation_type, _sid in counts_res.all():
        if relation_type in counts[stock_id]:
            counts[stock_id][relation_type] += 1

    items: list[SupplyChainCoverageItem] = []
    complete_count = 0
    partial_count = 0
    missing_count = 0
    for stock in stocks:
        c = counts[stock.id]
        total = c["upstream"] + c["downstream"] + c["competitor"]
        is_complete = (
            c["upstream"] >= min_upstream
            and c["downstream"] >= min_downstream
            and c["competitor"] >= min_competitors
        )
        if is_complete:
            status = "complete"
            complete_count += 1
        elif total > 0:
            status = "partial"
            partial_count += 1
        else:
            status = "missing"
            missing_count += 1

        items.append(SupplyChainCoverageItem(
            code=stock.code,
            name=stock.name or stock.code,
            upstream_count=c["upstream"],
            downstream_count=c["downstream"],
            competitor_count=c["competitor"],
            total_count=total,
            status=status,
        ))

    return SupplyChainCoverageResponse(
        items=items,
        stats={
            "watchlist_count": len(items),
            "complete_count": complete_count,
            "partial_count": partial_count,
            "missing_count": missing_count,
            "gap_count": partial_count + missing_count,
        },
    )


async def get_supply_chain_gap_codes(
    db: AsyncSession,
    *,
    force: bool = False,
    min_upstream: int = 1,
    min_downstream: int = 1,
    min_competitors: int = 1,
) -> list[str]:
    """返回需要补齐供应链关系的自选股代码。"""
    coverage = await get_supply_chain_coverage(
        db,
        min_upstream=min_upstream,
        min_downstream=min_downstream,
        min_competitors=min_competitors,
    )
    if force:
        return [item.code for item in coverage.items]
    return [item.code for item in coverage.items if item.status != "complete"]


async def link_news_to_supply_chain(
    db: AsyncSession,
    news: IndustryNews,
    *,
    importance: float | None = None,
    urgency: str | None = None,
) -> int:
    """将资讯匹配到供应链合作方，并反向关联到对应自选股。"""
    text = f"{news.title or ''} {news.content or ''} {news.summary or ''}"
    if not text.strip():
        return 0

    rows = await db.execute(
        select(SupplyChain, Stock.code, Stock.name, Stock.market)
        .join(Stock, Stock.id == SupplyChain.stock_id)
        .where(SupplyChain.relation_type.in_(["upstream", "downstream", "competitor"]))
    )

    inserted = 0
    seen: set[tuple[int, int]] = set()
    for sc, stock_code, stock_name, stock_market in rows.all():
        aliases = [sc.company_name]
        if sc.company_code:
            aliases.append(sc.company_code)
        matched_alias = next((a for a in aliases if _text_contains_alias(text, a)), None)
        if not matched_alias:
            continue

        company_id = await _get_or_create_company(
            db,
            name=sc.company_name,
            stock_code=sc.company_code,
            is_listed=bool(sc.is_listed),
        )
        key = (sc.stock_id, company_id)
        if key in seen:
            continue
        seen.add(key)

        relationship_id = (
            await db.execute(
                select(SupplyChainRelationship.id)
                .where(SupplyChainRelationship.legacy_supply_chain_id == sc.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if relationship_id is None:
            relationship_id = await _sync_legacy_relationship(
                db,
                stock_id=sc.stock_id,
                stock_code=stock_code,
                stock_name=stock_name,
                stock_market=stock_market,
                legacy=sc,
            )

        relevance = 0.7 if sc.importance == "high" else 0.55 if sc.importance == "medium" else 0.4
        if importance is not None:
            relevance = max(relevance, min(1.0, importance))

        link_stmt = (
            pg_insert(SupplyChainNewsLink)
            .values(
                news_id=news.id,
                stock_id=sc.stock_id,
                company_id=company_id,
                relationship_id=relationship_id,
                supply_chain_id=sc.id,
                matched_alias=matched_alias[:120],
                relevance=round(relevance, 4),
                impact_direction=news.direction,
                impact_summary=news.catalyst_summary or news.summary,
            )
            .on_conflict_do_update(
                index_elements=["news_id", "stock_id", "company_id"],
                set_={
                    "relationship_id": relationship_id,
                    "supply_chain_id": sc.id,
                    "matched_alias": matched_alias[:120],
                    "relevance": round(relevance, 4),
                    "impact_direction": news.direction,
                    "impact_summary": news.catalyst_summary or news.summary,
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        result = await db.execute(link_stmt)
        if result.rowcount:
            inserted += 1

        await db.execute(
            pg_insert(NewsStockRelation)
            .values(news_id=news.id, stock_id=sc.stock_id, relevance=round(relevance, 4))
            .on_conflict_do_update(
                index_elements=["news_id", "stock_id"],
                set_={"relevance": round(relevance, 4)},
            )
        )

        if (urgency in {"urgent", "important"}) or (importance is not None and importance >= 0.5):
            dedup = hashlib.sha256(f"supply-chain:{news.id}:{company_id}".encode()).hexdigest()[:32]
            title = f"供应链动态: {sc.company_name}"
            await db.execute(
                pg_insert(StockEvent)
                .values(
                    stock_id=sc.stock_id,
                    event_type="SUPPLY_CHAIN_NEWS",
                    severity="high" if urgency == "urgent" else "medium",
                    dedup_key=dedup,
                    title=title[:200],
                    payload={
                        "news_id": news.id,
                        "company_name": sc.company_name,
                        "company_code": sc.company_code,
                        "relation_type": sc.relation_type,
                        "product_desc": sc.product_desc,
                        "news_title": news.title,
                        "importance_score": importance,
                    },
                )
                .on_conflict_do_nothing(
                    index_elements=["stock_id", "event_type", "dedup_key"]
                )
            )

    if inserted:
        logger.info(f"[supply_chain_news] news_id={news.id} 关联 {inserted} 条供应链关系")
    return inserted


async def materialize_supply_chain_relationships(db: AsyncSession) -> int:
    """将旧 supply_chains 表同步到实体化关系表。"""
    rows = await db.execute(
        select(SupplyChain, Stock.code, Stock.name, Stock.market)
        .join(Stock, Stock.id == SupplyChain.stock_id)
    )
    count = 0
    for sc, stock_code, stock_name, stock_market in rows.all():
        relationship_id = await _sync_legacy_relationship(
            db,
            stock_id=sc.stock_id,
            stock_code=stock_code,
            stock_name=stock_name,
            stock_market=stock_market,
            legacy=sc,
        )
        if relationship_id:
            count += 1
    await db.flush()
    return count


async def backfill_recent_supply_chain_news_links(
    db: AsyncSession,
    *,
    days: int = 14,
    limit: int = 500,
) -> int:
    """回填近期已处理资讯与供应链关系的关联。"""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = await db.execute(
        select(IndustryNews)
        .where(IndustryNews.published_at >= cutoff)
        .where(IndustryNews.processed_at.isnot(None))
        .order_by(IndustryNews.published_at.desc())
        .limit(limit)
    )
    total = 0
    for news in rows.scalars().all():
        total += await link_news_to_supply_chain(
            db,
            news,
            importance=float(news.importance_score) if news.importance_score is not None else None,
            urgency=news.urgency,
        )
    await db.flush()
    return total


class SupplyChainService:
    """供应链提取服务（年报 PDF → AI → 数据库）"""

    async def extract_and_save(
        self,
        db: AsyncSession,
        code: str,
        *,
        use_annual_report: bool = True,
    ) -> list[SupplyChain]:
        from sqlalchemy import delete

        from app.services.ai_analyzer.supply_chain_extractor import SupplyChainExtractor

        # 获取股票名称
        result = await db.execute(select(Stock.id, Stock.name, Stock.market).where(Stock.code == code))
        row = result.first()
        if not row:
            return []
        stock_id, name, market = row.id, row.name or code, row.market

        # 尝试获取年报文本（可选，失败不影响 AI 提取）。
        # 批量补齐时先跳过年报下载，快速铺底层供应链骨架；单股刷新再用年报增强。
        text = ""
        if use_annual_report:
            try:
                from app.services.data_fetcher.annual_report_fetcher import AnnualReportFetcher
                fetcher = AnnualReportFetcher()
                text = await fetcher.fetch_report_text(code)
            except Exception as e:
                logger.warning(f"[{code}] 年报获取失败，使用 AI 知识库: {e}")

        # AI 提取（基于公开资料+模型知识）
        extractor = SupplyChainExtractor()
        chain_data = await extractor.extract(code, name, text, db=db)
        if not chain_data:
            logger.warning(f"[{code}] AI 未提取到供应链数据")
            return []

        # 清除旧数据后写入（全量替换）
        await db.execute(delete(SupplyChain).where(SupplyChain.stock_id == stock_id))
        saved = []
        for item in chain_data:
            node = SupplyChain(stock_id=stock_id, **item)
            db.add(node)
            await db.flush()
            await _sync_legacy_relationship(
                db,
                stock_id=stock_id,
                stock_code=code,
                stock_name=name,
                stock_market=market,
                legacy=node,
            )
            saved.append(node)

        await db.flush()
        logger.info(f"[{code}] 供应链写入 {len(saved)} 条")
        return saved
