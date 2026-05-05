"""数据采集相关 Celery 任务"""
import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.data_tasks.backfill_stock_data", bind=True, max_retries=3)
def backfill_stock_data(self, stock_code: str, market: str = "A", days: int = 200):
    """新增自选股时回填历史数据（K线 + 技术指标 + 财务），完成后触发 AI 报告"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.kline_service import save_klines
        from app.services.fundamental_service import save_fundamental
        from app.services.stock_service import mark_data_ready
        from app.services.analysis.technical_analyzer import TechnicalAnalyzer
        from app.tasks.analysis_tasks import generate_report_task

        async with AsyncSessionLocal() as db:
            fetcher = AKShareFetcher()

            # 1. 回填 K 线（多取数据保证 MA60 有足够历史）
            klines = await fetcher.fetch_daily_kline(stock_code, market=market, days=days)
            saved = await save_klines(db, stock_code, klines)
            logger.info(f"[{stock_code}] 回填 K 线 {saved} 条")

            # 2. 立即计算技术指标（MA / MACD / RSI / KDJ / 布林带）
            try:
                analyzer = TechnicalAnalyzer()
                ind_saved = await analyzer.calc_and_save(db, stock_code)
                await db.commit()
                logger.info(f"[{stock_code}] 技术指标计算完成，写入 {ind_saved} 条")
            except Exception as e:
                logger.error(f"[{stock_code}] 技术指标计算失败: {e}")

            # 3. 基本面数据
            fundamental = await fetcher.fetch_fundamental(stock_code, market=market)
            if fundamental:
                await save_fundamental(db, stock_code, fundamental)
                await db.commit()
                logger.info(f"[{stock_code}] 基本面数据写入完成")

            # 4. 标记数据就绪
            await mark_data_ready(db, stock_code)
            await db.commit()
            logger.info(f"[{stock_code}] data_ready = True")

        # 5. 触发首份 AI 报告（指标已就绪）
        generate_report_task.delay(stock_code, "initial")

        # 6. 触发供应链提取（A股）
        if market == "A":
            from app.tasks.supply_chain_tasks import extract_supply_chain_task
            extract_supply_chain_task.delay(stock_code)

        # 注：标签生成已改为纯手动。详情页"AI 试生成"按钮仍可手动触发，
        # 但不再在 backfill 链尾自动调用（AI 准确率不足，让用户主导）

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[{stock_code}] 回填数据失败: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.tasks.data_tasks.sync_universe_basic_data", bind=True, max_retries=0)
def sync_universe_basic_data(self, days: int = 120, max_stocks: int | None = None):
    """全 A 股基础数据同步（仅 K 线 + 最新财报，不入自选股）

    用途：建立"备用研究池"，加自选股前可先看历史与基本面。
    每周日凌晨跑一次，约 5500 只股票 × ~1.5s ≈ 2.3 小时。
    单股失败仅日志，不 raise（保持 max_retries=0 + retry-loop in body）。
    """
    asyncio.run(_sync_universe_run(days=days, max_stocks=max_stocks))


async def _sync_universe_run(days: int = 120, max_stocks: int | None = None):
    import time
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.core.database import AsyncSessionLocal
    from app.models.stock import Stock
    from app.models.stock_universe import StockUniverse
    from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
    from app.services.fundamental_service import save_fundamental
    from app.services.kline_service import save_klines

    fetcher = AKShareFetcher()

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(StockUniverse.code, StockUniverse.name, StockUniverse.market)
            .where(StockUniverse.market == "A")
            .order_by(StockUniverse.code)
        )
        universe = list(res.all())

    if max_stocks:
        universe = universe[:max_stocks]

    total = len(universe)
    logger.info(f"[sync_universe] 开始同步 {total} 只 A 股（{days} 天 K 线 + 最新财报）")

    started = time.time()
    succeeded = 0
    failed = 0

    for idx, (code, name, market) in enumerate(universe, 1):
        try:
            # 1. 确保 stocks 表里有该股（is_watchlist=False，不影响自选股）
            async with AsyncSessionLocal() as db:
                stmt = pg_insert(Stock).values(
                    code=code,
                    market=market,
                    name=name or code,
                    is_watchlist=False,
                    data_ready=False,
                ).on_conflict_do_nothing(index_elements=["code"])
                await db.execute(stmt)
                await db.commit()

            # 2. K 线（120 天）
            klines = await fetcher.fetch_daily_kline(code, market="A", days=days)
            if klines:
                async with AsyncSessionLocal() as db:
                    await save_klines(db, code, klines)
                    await db.commit()

            # 3. 最新财报
            try:
                fundamental = await fetcher.fetch_fundamental(code, market="A")
                if fundamental:
                    async with AsyncSessionLocal() as db:
                        await save_fundamental(db, code, fundamental)
                        await db.commit()
            except Exception as e:
                logger.debug(f"[sync_universe][{code}] 基本面跳过: {e}")

            succeeded += 1
            if idx % 100 == 0:
                elapsed = time.time() - started
                logger.info(
                    f"[sync_universe] 进度 {idx}/{total} ({idx * 100 / total:.1f}%) "
                    f"成功 {succeeded} 失败 {failed} 已用时 {elapsed / 60:.1f} 分"
                )
        except Exception as e:
            failed += 1
            logger.warning(f"[sync_universe][{code}] 失败跳过: {e}")
            continue

    elapsed = time.time() - started
    logger.info(
        f"[sync_universe] 完成。成功 {succeeded}/{total} 失败 {failed}，"
        f"用时 {elapsed / 60:.1f} 分"
    )


@celery_app.task(name="app.tasks.data_tasks.update_realtime_quotes")
def update_realtime_quotes():
    """更新自选股实时行情（交易时段每15秒）"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.stock_service import get_all_watchlist_codes
        from app.services.quote_cache import update_quote_cache

        if not _is_trading_time():
            return

        async with AsyncSessionLocal() as db:
            codes = await get_all_watchlist_codes(db)
            if not codes:
                return
            fetcher = AKShareFetcher()
            quotes = await fetcher.fetch_realtime_quotes(codes)
            await update_quote_cache(quotes)

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.update_all_fundamentals")
def update_all_fundamentals():
    """更新所有自选股基本面数据"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.stock_service import get_all_watchlist_codes
        from app.services.fundamental_service import save_fundamental

        async with AsyncSessionLocal() as db:
            codes = await get_all_watchlist_codes(db)
            fetcher = AKShareFetcher()
            for code in codes:
                try:
                    data = await fetcher.fetch_fundamental(code)
                    await save_fundamental(db, code, data)
                    await asyncio.sleep(0.5)  # AKShare 限速
                except Exception as e:
                    logger.error(f"[{code}] 更新基本面失败: {e}")
            await db.commit()

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.sync_stock_universe", bind=True, max_retries=3)
def sync_stock_universe(self):
    """同步全量 A股 + 港股 列表到本地数据库（每周日凌晨2点）"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_universe_service import sync_stock_universe as _sync

        async with AsyncSessionLocal() as db:
            result = await _sync(db)
            logger.info(f"[Universe] Celery 同步完成: {result}")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error(f"[Universe] 同步失败: {exc}")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="app.tasks.data_tasks.update_capital_flows")
def update_capital_flows():
    """每日 17:00：拉取所有自选股北上资金日度，写 stock_capital_flows"""
    async def _run():
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.core.database import AsyncSessionLocal
        from app.models.capital_flow import StockCapitalFlow
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.stock_service import get_all_watchlist_codes_with_info

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)
            fetcher = AKShareFetcher()
            saved_total = 0
            for s in stocks:
                if s.get("market") != "A":  # 北上资金只针对 A股
                    continue
                try:
                    rows = await fetcher.fetch_capital_flows(s["code"])
                except Exception as e:
                    logger.error(f"[capital_flows][{s['code']}] 抓取失败: {e}")
                    continue
                for r in rows:
                    stmt = pg_insert(StockCapitalFlow).values(
                        stock_id=s["id"],
                        trade_date=r["trade_date"],
                        net_inflow=r.get("net_inflow"),
                        shareholding_ratio=r.get("shareholding_ratio"),
                        shareholding_volume=r.get("shareholding_volume"),
                    ).on_conflict_do_update(
                        index_elements=["stock_id", "trade_date"],
                        set_={
                            "net_inflow": r.get("net_inflow"),
                            "shareholding_ratio": r.get("shareholding_ratio"),
                            "shareholding_volume": r.get("shareholding_volume"),
                        },
                    )
                    await db.execute(stmt)
                saved_total += len(rows)
            await db.commit()
            logger.info(f"[update_capital_flows] 写入 {saved_total} 行")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.update_lhb")
def update_lhb():
    """每日 17:00：拉取当日龙虎榜（只保留自选股入榜）"""
    async def _run():
        from datetime import date
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.core.database import AsyncSessionLocal
        from app.models.lhb import StockLhb
        from app.models.stock import Stock
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher

        async with AsyncSessionLocal() as db:
            fetcher = AKShareFetcher()
            try:
                rows = await fetcher.fetch_lhb(date.today())
            except Exception as e:
                logger.error(f"[lhb] 抓取失败: {e}")
                return

            # 过滤自选股
            wl = await db.execute(
                select(Stock.id, Stock.code).where(Stock.is_watchlist.is_(True))
            )
            code_to_id = {c: i for i, c in wl.all()}

            saved = 0
            for r in rows:
                sid = code_to_id.get(r["code"])
                if not sid:
                    continue
                stmt = pg_insert(StockLhb).values(
                    stock_id=sid,
                    trade_date=r["trade_date"],
                    reason=r.get("reason"),
                    buy_amount=r.get("buy_amount"),
                    sell_amount=r.get("sell_amount"),
                    net_amount=r.get("net_amount"),
                    change_pct=r.get("change_pct"),
                ).on_conflict_do_nothing(index_elements=["stock_id", "trade_date"])
                await db.execute(stmt)
                saved += 1
            await db.commit()
            logger.info(f"[update_lhb] 自选股入榜 {saved} 行")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.sync_calendar_events")
def sync_calendar_events():
    """每周日：同步财报披露日历 + 解禁日历（未来 90 天）"""
    async def _run():
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from app.core.database import AsyncSessionLocal
        from app.models.calendar_event import CalendarEvent
        from app.models.stock import Stock
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher

        async with AsyncSessionLocal() as db:
            fetcher = AKShareFetcher()
            wl = await db.execute(
                select(Stock.id, Stock.code).where(Stock.is_watchlist.is_(True))
            )
            code_to_id = {c: i for i, c in wl.all()}

            saved = 0
            # 财报披露
            try:
                disc = await fetcher.fetch_disclosure_calendar()
            except Exception as e:
                logger.error(f"[calendar] 披露日历抓取失败: {e}")
                disc = []
            for d in disc:
                sid = code_to_id.get(d["code"])
                if not sid:
                    continue
                stmt = pg_insert(CalendarEvent).values(
                    stock_id=sid,
                    event_type="earnings_release",
                    event_date=d["event_date"],
                    title=d["title"],
                    source=d.get("source"),
                ).on_conflict_do_nothing(
                    index_elements=["stock_id", "event_type", "event_date"]
                )
                await db.execute(stmt)
                saved += 1

            # 解禁
            try:
                rel = await fetcher.fetch_restricted_release()
            except Exception as e:
                logger.error(f"[calendar] 解禁日历抓取失败: {e}")
                rel = []
            for r in rel:
                sid = code_to_id.get(r["code"])
                if not sid:
                    continue
                stmt = pg_insert(CalendarEvent).values(
                    stock_id=sid,
                    event_type="restricted_release",
                    event_date=r["event_date"],
                    title=r["title"],
                    payload=r.get("payload"),
                    source=r.get("source"),
                ).on_conflict_do_nothing(
                    index_elements=["stock_id", "event_type", "event_date"]
                )
                await db.execute(stmt)
                saved += 1

            await db.commit()
            logger.info(f"[sync_calendar_events] 写入 {saved} 行（含已存在的去重）")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.update_profit_forecasts")
def update_profit_forecasts():
    """对所有自选股刷新盈利预测(优先同花顺真实数据,降级 LLM)"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.stock_service import get_all_watchlist_codes
        from app.services.ai_analyzer.forecast_generator import update_profit_forecasts as upd

        async with AsyncSessionLocal() as db:
            codes = await get_all_watchlist_codes(db)
            stats = {"ths": 0, "llm": 0, "skipped": 0, "fail": 0}
            for code in codes:
                try:
                    r = await upd(db, code)
                    stats[r["source"]] = stats.get(r["source"], 0) + 1
                    await db.commit()
                except Exception as e:
                    stats["fail"] += 1
                    logger.error(f"[{code}] 盈利预测刷新失败: {e}")
                    await db.rollback()
                await asyncio.sleep(0.5)  # AKShare 限速
            logger.info(f"[update_profit_forecasts] 完成: {stats}")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.update_industry_metrics")
def update_industry_metrics():
    """每月 1 日：抓 NVDA + 4 大 CSP 最新 10-Q，AI 提取数据中心/Capex 关键指标"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher import industry_report_fetcher as irf
        from app.services.ai_analyzer import industry_metrics_extractor as ime

        async with AsyncSessionLocal() as db:
            total = 0
            for ticker in ["NVDA", "GOOGL", "META", "MSFT", "AMZN"]:
                try:
                    filing = await irf.get_latest_10q(ticker)
                    if not filing:
                        logger.info(f"[industry_metrics][{ticker}] 找不到 10-Q")
                        continue
                    text = await irf.download_filing_text(filing)
                    if not text:
                        continue
                    period_hint = filing.filing_date[:7]
                    metrics = await ime.extract(db, ticker, text, period_hint)
                    if not metrics:
                        continue
                    n = await ime.save_metrics(
                        db, metrics, source="10-Q", extracted_from=filing.accession,
                    )
                    total += n
                    logger.info(f"[industry_metrics][{ticker}] 提取 {n} 项指标")
                except Exception as e:
                    logger.error(f"[industry_metrics][{ticker}] 失败: {e}")
            await db.commit()
            logger.info(f"[update_industry_metrics] 总计写入 {total} 项指标")

    asyncio.run(_run())


def _is_trading_time() -> bool:
    """判断当前是否在 A股交易时段（9:30-11:30 / 13:00-15:00，工作日）"""
    from datetime import datetime
    import pytz

    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)

    if now.weekday() >= 5:  # 周六、周日
        return False

    t = now.time()
    from datetime import time
    morning = time(9, 30) <= t <= time(11, 30)
    afternoon = time(13, 0) <= t <= time(15, 0)
    return morning or afternoon
