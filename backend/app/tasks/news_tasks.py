"""资讯流水线 Celery 任务

四阶段：
  1. crawl_all_sources       — 每 3 小时，抓取并写入 industry_news（processed_at=NULL）
  2. crawl_disclosures_only  — 每 30 分钟，财报公告专项
  3. process_pending_news    — 每 5 分钟，对未处理资讯跑 dedup→entity→规则打分→LLM→分级
  4. dispatch_important_summary — 每整点，推送 Redis 暂存的重要资讯
  5. dispatch_daily_summary  — 每日 8:00，推送当日摘要
"""
import asyncio
import hashlib
import logging
from datetime import datetime

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 1. 抓取阶段（与之前基本一致；processed_at 留空，由 process 阶段消费）
# ════════════════════════════════════════════════════════════════

@celery_app.task(name="app.tasks.news_tasks.crawl_research_reports")
def crawl_research_reports():
    """每日盘前盘后爬取所有自选股的券商研报元数据"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_service import get_all_watchlist_codes_with_info

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)
            total = 0
            for stock in stocks:
                try:
                    saved = await _fetch_and_save_research(db, stock["code"], stock["id"])
                    total += saved
                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.error(f"[{stock['code']}] 研报抓取失败: {e}")
            await db.commit()
            if total:
                logger.info(f"研报爬取完成，新增 {total} 条")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.news_tasks.process_research_pdfs")
def process_research_pdfs():
    """下载研报 PDF → 文本提取 → LLM 摘要 → 写回 industry_news.content/summary"""
    asyncio.run(_process_research_pdfs_run(limit=10))


async def _process_research_pdfs_run(limit: int = 10):
    from pathlib import Path

    from sqlalchemy import select, update

    from app.core.database import AsyncSessionLocal
    from app.models.news import IndustryNews
    from app.services.ai_analyzer.llm_client import call_llm
    from app.services.data_fetcher.pdf_utils import (
        download_pdf, pdf_to_text_async,
    )

    base_dir = Path("/app/data/research_reports")

    async with AsyncSessionLocal() as db:
        # 找 category=research 且 content 还未填充的
        res = await db.execute(
            select(IndustryNews.id, IndustryNews.source_url, IndustryNews.title)
            .where(IndustryNews.category == "research")
            .where(IndustryNews.content.is_(None))
            .where(IndustryNews.source_url.isnot(None))
            .order_by(IndustryNews.id.desc())
            .limit(limit)
        )
        rows = list(res.all())

    if not rows:
        return

    logger.info(f"[research_pdf] 待处理 {len(rows)} 条")
    succeeded = 0

    for news_id, url, title in rows:
        if not url or "pdf" not in url.lower():
            # 写一个占位避免下次重复
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(IndustryNews)
                    .where(IndustryNews.id == news_id)
                    .values(content="[无 PDF 链接]")
                )
                await db.commit()
            continue

        dest = base_dir / f"{news_id}.pdf"
        ok = await download_pdf(url, dest)
        if not ok:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(IndustryNews)
                    .where(IndustryNews.id == news_id)
                    .values(content="[PDF 下载失败]")
                )
                await db.commit()
            continue

        text = await pdf_to_text_async(dest, max_pages=40, max_chars=12000)
        if not text or len(text) < 100:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(IndustryNews)
                    .where(IndustryNews.id == news_id)
                    .values(content="[PDF 文本提取失败]")
                )
                await db.commit()
            continue

        # LLM 摘要（失败不阻塞）
        summary: str | None = None
        try:
            async with AsyncSessionLocal() as db_for_llm:
                prompt = (
                    f"以下是一篇券商研报《{title}》的正文。请用 100~200 字提炼研报核心观点：\n"
                    "1) 投资建议（评级 / 目标价）\n"
                    "2) 关键预测（业绩 / 增长 / EPS）\n"
                    "3) 主要逻辑（驱动力 / 催化）\n"
                    "4) 风险点\n\n"
                    "输出纯文本，不要 markdown 标题，每条用顿号分隔。\n\n"
                    f"研报正文（已截断）：\n{text}"
                )
                summary = await call_llm(
                    db_for_llm, prompt, max_tokens=400, prefer_haiku=True,
                )
                if summary:
                    summary = summary.strip()[:1000]
        except Exception as e:
            logger.warning(f"[research_pdf][{news_id}] LLM 摘要失败: {e}")

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(IndustryNews)
                .where(IndustryNews.id == news_id)
                .values(content=text, summary=summary)
            )
            await db.commit()
            succeeded += 1

    logger.info(f"[research_pdf] 处理完成，成功 {succeeded}/{len(rows)}")


@celery_app.task(name="app.tasks.news_tasks.crawl_disclosures_only")
def crawl_disclosures_only():
    """每30分钟专项爬取财报公告"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_service import get_all_watchlist_codes_with_info

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)
            total = 0
            for stock in stocks:
                try:
                    saved = await _fetch_and_save_disclosures(db, stock["code"], stock["id"])
                    total += saved
                    await asyncio.sleep(1.0)
                except Exception as e:
                    logger.error(f"[{stock['code']}] 财报公告爬取失败: {e}")
            await db.commit()
            if total:
                logger.info(f"财报公告专项爬取完成，新增 {total} 条")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.news_tasks.crawl_all_sources")
def crawl_all_sources():
    """每3小时爬取所有自选股资讯 + 财报公告。仅入库，打分由 process 阶段处理。"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_service import get_all_watchlist_codes_with_info

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)
            for stock in stocks:
                try:
                    saved = await _fetch_and_save_stock_news(db, stock["code"], stock["id"])
                    logger.info(f"[{stock['code']}] 资讯抓取完成，新增 {saved} 条")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[{stock['code']}] 资讯抓取失败: {e}")

                try:
                    disc_saved = await _fetch_and_save_disclosures(db, stock["code"], stock["id"])
                    if disc_saved:
                        logger.info(f"[{stock['code']}] 财报公告新增 {disc_saved} 条")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"[{stock['code']}] 财报公告抓取失败: {e}")

            await db.commit()

    asyncio.run(_run())


async def _fetch_and_save_research(db, code: str, stock_id: int) -> int:
    """券商研报:AKShare(主) + Claude web_search(增量补充近 7 天) → IndustryNews + ResearchReportMeta + NewsStockRelation"""
    from datetime import timedelta as _timedelta
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.news import IndustryNews, NewsStockRelation
    from app.models.research import ResearchReportMeta
    from app.services.news_crawler.research_crawler import ResearchCrawler

    # ── 1) AKShare 主源 ─────────────────────────────────────────
    crawler = ResearchCrawler()
    items = await crawler.fetch_by_code(code, days=30, limit=20)

    # ── 2) Claude web_search 增量补充(近 7 天) ───────────────────
    # 先收集已有标题(近 14 天)用于 LLM 去重提示
    cutoff_seen = datetime.now() - _timedelta(days=14)
    seen_res = await db.execute(
        select(IndustryNews.title)
        .where(IndustryNews.category == "research")
        .where(IndustryNews.published_at >= cutoff_seen)
    )
    seen_titles = [r[0] for r in seen_res.all() if r[0]]

    # 取股票名(用于 web_search prompt)
    from app.models.stock import Stock
    name_res = await db.execute(select(Stock.name).where(Stock.id == stock_id))
    stock_name = name_res.scalar_one_or_none() or code

    try:
        from app.services.data_fetcher.research_websearch_fetcher import (
            fetch_research_via_websearch,
        )
        ws_items = await fetch_research_via_websearch(
            db=db, code=code, name=stock_name, days=7,
            seen_titles=seen_titles, max_searches=5,
        )
        # 把 web_search 结果转成与 ResearchCrawler 输出一致的格式
        for ws in ws_items:
            items.append({
                "title": ws["title"],
                "content": ws.get("summary"),  # web_search 已带核心观点摘要
                "source": "web_search",
                "source_url": ws.get("source_url") or ws.get("pdf_url"),
                "published_at": datetime.combine(ws["published_at"], datetime.min.time())
                                if ws.get("published_at") else None,
                "source_authority": 0.80,  # 略低于 AKShare 主源
                "_meta": {
                    "_dedup_key": f"research:{code}:{ws['title']}",
                    "broker": ws.get("broker"),
                    "rating": ws.get("rating"),
                    "forecast_year_base": ws.get("forecast_year_base"),
                    "eps_y1": ws.get("eps_y1"),
                    "eps_y2": ws.get("eps_y2"),
                    "eps_y3": ws.get("eps_y3"),
                    "pe_y1": ws.get("pe_y1"),
                    "pe_y2": ws.get("pe_y2"),
                    "pe_y3": ws.get("pe_y3"),
                    "pdf_url": ws.get("pdf_url"),
                },
            })
    except Exception as e:
        logger.warning(f"[research_websearch][{code}] web_search 补充失败(忽略): {e}")

    # ── 3) 写库(已统一格式) ─────────────────────────────────────
    saved = 0
    for item in items:
        meta = item.get("_meta") or {}
        dedup_key = meta.get("_dedup_key") or f"research:{code}:{item['title']}"
        content_hash = hashlib.sha256(dedup_key.encode()).hexdigest()

        stmt = pg_insert(IndustryNews).values(
            title=item["title"],
            content=item.get("content"),
            source=item["source"],
            source_url=item.get("source_url"),
            published_at=item["published_at"] or datetime.now(),
            content_hash=content_hash,
            related_industries=[],
            category="research",
            source_authority=item.get("source_authority", 0.85),
        ).on_conflict_do_nothing(index_elements=["content_hash"])
        result = await db.execute(stmt)

        news_row = await db.execute(
            select(IndustryNews.id).where(IndustryNews.content_hash == content_hash)
        )
        news_id = news_row.scalar_one_or_none()
        if not news_id:
            continue

        # 强相关：研报本身就是单股的
        rel_stmt = pg_insert(NewsStockRelation).values(
            news_id=news_id, stock_id=stock_id, relevance=1.0,
        ).on_conflict_do_nothing()
        await db.execute(rel_stmt)

        # 写扩展元信息（与 news_id 一对一，幂等）
        meta_stmt = pg_insert(ResearchReportMeta).values(
            news_id=news_id,
            stock_id=stock_id,
            broker=meta.get("broker") or "",
            rating=meta.get("rating"),
            forecast_year_base=meta.get("forecast_year_base"),
            eps_y1=meta.get("eps_y1"),
            eps_y2=meta.get("eps_y2"),
            eps_y3=meta.get("eps_y3"),
            pe_y1=meta.get("pe_y1"),
            pe_y2=meta.get("pe_y2"),
            pe_y3=meta.get("pe_y3"),
            pdf_url=meta.get("pdf_url"),
        ).on_conflict_do_nothing(index_elements=["news_id"])
        await db.execute(meta_stmt)

        if result.rowcount:
            saved += 1

    await db.flush()
    return saved


async def _fetch_and_save_disclosures(db, code: str, stock_id: int) -> int:
    """财报公告：来源权威，初始 relevance=1.0，作为兜底关联"""
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.news import IndustryNews, NewsStockRelation
    from app.services.news_crawler.disclosure_crawler import DisclosureCrawler

    crawler = DisclosureCrawler()
    items = await crawler.fetch_by_code(code, limit=20)
    saved = 0

    for item in items:
        title = item["title"]
        content_hash = hashlib.sha256(f"disclosure:{code}:{title}".encode()).hexdigest()

        stmt = pg_insert(IndustryNews).values(
            title=title,
            content=item.get("content"),
            source=item["source"],
            source_url=item.get("source_url"),
            published_at=item["published_at"] or datetime.now(),
            content_hash=content_hash,
            related_industries=[],
            category=item.get("category", "announcement"),
            source_authority=item.get("source_authority", 1.0),
        ).on_conflict_do_nothing(index_elements=["content_hash"])
        result = await db.execute(stmt)

        from sqlalchemy import select
        news_row = await db.execute(
            select(IndustryNews.id).where(IndustryNews.content_hash == content_hash)
        )
        news_id = news_row.scalar_one_or_none()
        if not news_id:
            continue

        # 财报公告强相关：兜底建关联（process 阶段会用 LLM 修正 relevance）
        rel_stmt = pg_insert(NewsStockRelation).values(
            news_id=news_id, stock_id=stock_id, relevance=1.0,
        ).on_conflict_do_nothing()
        await db.execute(rel_stmt)

        if result.rowcount:
            saved += 1

    await db.flush()
    return saved


async def _fetch_and_save_stock_news(db, code: str, stock_id: int) -> int:
    """单股资讯入库（不建 relation；由 process 阶段按实体匹配建立）"""
    import akshare as ak
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.news import IndustryNews

    df = await asyncio.to_thread(ak.stock_news_em, symbol=code)
    if df.empty:
        return 0

    saved = 0
    for _, row in df.iterrows():
        title = str(row.get("新闻标题", "") or "").strip()
        if not title:
            continue

        content = str(row.get("新闻内容", "") or "").strip() or None
        url = str(row.get("新闻链接", "") or "").strip() or None
        source = str(row.get("文章来源", "") or "eastmoney").strip()[:50]
        date_str = str(row.get("发布时间", "") or "")
        try:
            published_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            published_at = datetime.now()

        content_hash = hashlib.sha256(f"{source}:{title}".encode()).hexdigest()

        from app.services.news_crawler.base_crawler import SOURCE_AUTHORITY
        stmt = pg_insert(IndustryNews).values(
            title=title,
            content=content,
            source=source,
            source_url=url,
            published_at=published_at,
            content_hash=content_hash,
            related_industries=[],
            category="news",
            source_authority=SOURCE_AUTHORITY.get(source, 0.5),
        ).on_conflict_do_nothing(index_elements=["content_hash"])
        result = await db.execute(stmt)

        if result.rowcount:
            saved += 1

    await db.flush()
    return saved


# ════════════════════════════════════════════════════════════════
# 2. 处理阶段（去重 → 实体匹配 → 规则打分 → LLM → 分级 → 推送）
# ════════════════════════════════════════════════════════════════

PROCESS_BATCH_SIZE = 30  # 每次处理的资讯条数上限（控制 LLM 成本）


@celery_app.task(name="app.tasks.news_tasks.process_pending_news")
def process_pending_news():
    """每 5 分钟跑一次。对 processed_at IS NULL 的资讯执行完整打分流水线。"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            count = await _process_pipeline(db)
            inserted = await _extract_insider_trades(db)
            await db.commit()
            if count or inserted:
                logger.info(
                    f"[process_pending_news] 资讯 {count} 条，减持/增持入库 {inserted} 条"
                )

    asyncio.run(_run())


INSIDER_TITLE_KEYWORDS = ("减持", "增持", "回购", "持股变动", "权益变动")


async def _extract_insider_trades(db) -> int:
    """对 announcement 类资讯标题命中减持/增持关键词的，批量调 LLM 提取入 insider_trades"""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.news import IndustryNews, NewsStockRelation
    from app.models.insider_trade import InsiderTrade
    from app.services.ai_analyzer import insider_extractor
    from app.models.stock import Stock

    # 取最近 24h 内 announcement 类、未处理过 insider 的资讯
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=24)
    rows = await db.execute(
        select(IndustryNews, NewsStockRelation.stock_id, Stock.code)
        .join(NewsStockRelation, NewsStockRelation.news_id == IndustryNews.id)
        .join(Stock, Stock.id == NewsStockRelation.stock_id)
        .where(IndustryNews.category == "announcement")
        .where(IndustryNews.processed_at >= cutoff)
        .limit(50)
    )
    candidates: list[insider_extractor.InsiderInput] = []
    news_meta: dict[int, tuple[int, str]] = {}  # idx -> (stock_id, news_id)
    seen_news_ids: set[int] = set()
    for news, stock_id, code in rows.all():
        if news.id in seen_news_ids:
            continue
        seen_news_ids.add(news.id)
        if not any(kw in (news.title or "") for kw in INSIDER_TITLE_KEYWORDS):
            continue
        # 已存在对应 insider_trade（同 news_id）则跳过
        existing = await db.execute(
            select(InsiderTrade.id).where(InsiderTrade.source_news_id == news.id).limit(1)
        )
        if existing.scalar_one_or_none():
            continue
        candidates.append(insider_extractor.InsiderInput(
            idx=news.id,
            code=code,
            title=news.title,
            content=news.content,
            ann_date=(news.published_at or news.crawled_at).date().isoformat(),
        ))
        news_meta[news.id] = (stock_id, news.id)

    if not candidates:
        return 0

    results = await insider_extractor.extract_batch(db, candidates)
    inserted = 0
    for r in results:
        if not r.is_insider or r.trade_type not in ("reduce", "increase"):
            continue
        meta = news_meta.get(r.idx)
        if not meta:
            continue
        stock_id, news_id = meta
        # ann_date 从 news 时间映射回 input
        cand = next((c for c in candidates if c.idx == r.idx), None)
        if not cand:
            continue
        from datetime import date as _date
        ann_date = _date.fromisoformat(cand.ann_date)
        stmt = pg_insert(InsiderTrade).values(
            stock_id=stock_id,
            ann_date=ann_date,
            trade_type=r.trade_type,
            holder_name=r.holder_name or "未知股东",
            shares=r.shares,
            pct_of_total=r.pct_of_total,
            price_low=r.price_low,
            price_high=r.price_high,
            source_news_id=news_id,
        ).on_conflict_do_nothing(
            index_elements=["stock_id", "ann_date", "trade_type", "holder_name"]
        )
        result = await db.execute(stmt)
        if result.rowcount:
            inserted += 1
    return inserted


async def _process_pipeline(db) -> int:
    """完整的 dedup → entity → rule → llm → urgency → notify 流水线"""
    from sqlalchemy import select, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.news import IndustryNews, NewsStockRelation
    from app.services.news_filter import dedup as dedup_mod
    from app.services.news_filter import entity_matcher
    from app.services.news_filter import keyword_builder
    from app.services.news_filter import llm_scorer
    from app.services.news_filter import rule_scorer
    from app.services.news_filter import urgency_classifier
    from app.services.notifier import dispatcher
    from app.models.stock import Stock

    # 1. 拉取待处理
    result = await db.execute(
        select(IndustryNews)
        .where(IndustryNews.processed_at.is_(None))
        .order_by(IndustryNews.id.asc())
        .limit(PROCESS_BATCH_SIZE)
    )
    pending: list[IndustryNews] = list(result.scalars().all())
    if not pending:
        return 0

    # 2. 关键词库（缓存）
    keywords_by_stock = await keyword_builder.get_keywords_cached(db)

    # stock_id -> name 映射（LLM prompt 用）
    stock_name_map: dict[int, str] = {}
    if keywords_by_stock:
        stock_rows = await db.execute(
            select(Stock.id, Stock.name).where(Stock.id.in_(keywords_by_stock.keys()))
        )
        stock_name_map = {sid: name for sid, name in stock_rows.all()}

    # 3. 第一遍：SimHash + 规则打分 + 实体匹配，过滤掉低分项
    llm_inputs: list[llm_scorer.LLMNewsInput] = []
    news_meta: dict[int, dict] = {}  # news_id -> {matches, simhash, rule_score, dup_id}
    for news in pending:
        text = f"{news.title} {news.content or ''}"

        # SimHash 跨源去重
        simhash = dedup_mod.compute_simhash(news.title)
        dup_id = None
        if simhash is not None:
            dup_id = await dedup_mod.find_duplicate(db, simhash, exclude_id=news.id)

        # 实体匹配
        matches = entity_matcher.match(text, keywords_by_stock) if keywords_by_stock else []

        # 规则打分
        rscore = rule_scorer.score(
            title=news.title,
            content=news.content,
            source=news.source,
            source_authority=news.source_authority,
        )

        news_meta[news.id] = {
            "matches": matches,
            "simhash": simhash,
            "rule_score": rscore,
            "dup_id": dup_id,
            "obj": news,
        }

        # 进 LLM 的条件：未重复 AND 规则分 ≥ 阈值 AND 至少匹配到一只自选股
        # （财报公告即使没匹配也保留——已有 disclosure 任务建好关联了）
        is_disclosure = news.category == "announcement"
        has_existing_rel = False
        if is_disclosure:
            check = await db.execute(
                select(NewsStockRelation.news_id)
                .where(NewsStockRelation.news_id == news.id)
                .limit(1)
            )
            has_existing_rel = check.scalar_one_or_none() is not None

        should_llm = (
            dup_id is None
            and rscore >= rule_scorer.LLM_THRESHOLD
            and (matches or has_existing_rel)
        )
        if should_llm:
            candidate_ids = (
                {m.stock_id for m in matches}
                if matches
                else set()
            )
            if has_existing_rel and not candidate_ids:
                # 财报公告兜底：取已有关联
                rel_rows = await db.execute(
                    select(NewsStockRelation.stock_id).where(
                        NewsStockRelation.news_id == news.id
                    )
                )
                candidate_ids = {r for (r,) in rel_rows.all()}

            candidate_stocks = {
                sid: stock_name_map.get(sid, str(sid)) for sid in candidate_ids
            }
            llm_inputs.append(
                llm_scorer.LLMNewsInput(
                    idx=news.id,
                    title=news.title,
                    content=news.content,
                    source=news.source,
                    candidate_stocks=candidate_stocks,
                )
            )

    # 4. LLM 批量打分
    llm_outputs: dict[int, llm_scorer.LLMNewsOutput] = {}
    if llm_inputs:
        results = await llm_scorer.score_batch(db, llm_inputs)
        llm_outputs = {r.idx: r for r in results}

    # 5. 回填 + 建关联 + 推送
    processed_count = 0
    for news_id, meta in news_meta.items():
        news: IndustryNews = meta["obj"]
        matches = meta["matches"]
        simhash = meta["simhash"]
        rscore = meta["rule_score"]
        dup_id = meta["dup_id"]
        llm_out: llm_scorer.LLMNewsOutput | None = llm_outputs.get(news_id)

        # 综合分
        if llm_out:
            importance = round(rscore * 0.4 + (llm_out.strength / 5) * 0.6, 4)
        else:
            importance = round(rscore, 4)

        urgency = urgency_classifier.classify(
            importance_score=importance, title=news.title
        )

        # 更新资讯字段
        await db.execute(
            update(IndustryNews)
            .where(IndustryNews.id == news_id)
            .values(
                simhash=simhash,
                rule_score=rscore,
                llm_score=float(llm_out.strength) if llm_out else None,
                importance_score=importance,
                direction=llm_out.direction if llm_out else None,
                sentiment=llm_out.sentiment if llm_out else None,
                summary=llm_out.summary if llm_out else news.summary,
                urgency=urgency,
                processed_at=datetime.now(),
            )
        )

        # 建立股票关联（实体匹配命中的）
        for m in matches:
            # 用 LLM 修正 relevance（如有）
            relevance = m.relevance
            if llm_out and m.stock_id in llm_out.stock_relevance:
                relevance = max(relevance, llm_out.stock_relevance[m.stock_id])
            rel_stmt = pg_insert(NewsStockRelation).values(
                news_id=news_id,
                stock_id=m.stock_id,
                relevance=round(min(1.0, relevance), 4),
            ).on_conflict_do_update(
                index_elements=["news_id", "stock_id"],
                set_={"relevance": round(min(1.0, relevance), 4)},
            )
            await db.execute(rel_stmt)

        # 兜底：财报公告已有关联，用 LLM relevance 修正
        if llm_out:
            await db.execute(
                update(NewsStockRelation)
                .where(NewsStockRelation.news_id == news_id)
                .where(NewsStockRelation.stock_id.in_(llm_out.stock_relevance.keys()))
                .values(relevance=NewsStockRelation.relevance)  # placeholder
            )
            for sid, rel in llm_out.stock_relevance.items():
                await db.execute(
                    update(NewsStockRelation)
                    .where(NewsStockRelation.news_id == news_id)
                    .where(NewsStockRelation.stock_id == sid)
                    .values(relevance=round(min(1.0, max(0.0, rel)), 4))
                )

        # 重复项：标记 processed 但不推送，可选合并关联（这里简化为不合并）
        if dup_id is not None:
            logger.debug(f"[process] news_id={news_id} 与 {dup_id} 近似重复，跳过推送")
        else:
            # 推送（urgent 立即；important 进队列）
            await db.flush()  # 确保读到刚才 update 的字段
            # 重新读出
            from sqlalchemy import select as _sel
            updated_row = await db.execute(
                _sel(IndustryNews).where(IndustryNews.id == news_id)
            )
            updated = updated_row.scalar_one()

            if urgency == "urgent":
                try:
                    await dispatcher.dispatch_urgent(db, updated)
                except Exception as e:
                    logger.error(f"[process] urgent 推送失败 news_id={news_id}: {e}")
            elif urgency == "important":
                related_rows = await db.execute(
                    _sel(NewsStockRelation.stock_id, NewsStockRelation.relevance)
                    .where(NewsStockRelation.news_id == news_id)
                    .order_by(NewsStockRelation.relevance.desc())
                )
                stock_ids = [sid for sid, _ in related_rows.all()]
                if stock_ids:
                    name_rows = await db.execute(
                        _sel(Stock.code, Stock.name).where(Stock.id.in_(stock_ids))
                    )
                    related = [(c, n) for c, n in name_rows.all()]
                else:
                    related = []
                try:
                    await dispatcher.queue_important(updated, related)
                except Exception as e:
                    logger.error(f"[process] important 入队失败 news_id={news_id}: {e}")

        processed_count += 1

    return processed_count


# ════════════════════════════════════════════════════════════════
# 3. 推送阶段
# ════════════════════════════════════════════════════════════════

@celery_app.task(name="app.tasks.news_tasks.dispatch_important_summary")
def dispatch_important_summary():
    """每整点：把 Redis 中堆积的重要级资讯一次性聚合推送"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.notifier import dispatcher

        async with AsyncSessionLocal() as db:
            n = await dispatcher.flush_important(db)
            if n:
                logger.info(f"[dispatch_important_summary] 推送 {n} 条重要资讯")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.news_tasks.dispatch_daily_summary")
def dispatch_daily_summary():
    """每日 8:00：摘要推送"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.notifier import dispatcher

        async with AsyncSessionLocal() as db:
            n = await dispatcher.send_daily_summary(db)
            logger.info(f"[dispatch_daily_summary] 摘要包含 {n} 条")

    asyncio.run(_run())
