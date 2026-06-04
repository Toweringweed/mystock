"""数据采集相关 Celery 任务"""
import asyncio
import logging
from datetime import UTC

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.data_tasks.backfill_stock_data", bind=True, max_retries=3)
def backfill_stock_data(self, stock_code: str, market: str = "A", days: int = 200):
    """新增自选股时回填历史数据（K线 + 技术指标 + 财务），完成后触发 AI 报告"""
    async def _run():
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.stock import Stock
        from app.services.analysis.technical_analyzer import TechnicalAnalyzer
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.fundamental_service import save_fundamental
        from app.services.kline_service import save_klines, update_volume_ratios
        from app.services.stock_service import mark_data_ready, mark_sync_running
        from app.tasks.analysis_tasks import generate_report_task

        async with AsyncSessionLocal() as db:
            fetcher = AKShareFetcher()

            # API 提交事务后才投递任务，但 worker 极快抢跑或手工投递时仍做一次兜底。
            for _ in range(10):
                stock_id = await db.scalar(select(Stock.id).where(Stock.code == stock_code))
                if stock_id:
                    break
                await asyncio.sleep(1)
            else:
                raise ValueError(f"[{stock_code}] 股票记录尚未提交，无法回填")
            task_id = getattr(self.request, "id", None)
            await mark_sync_running(db, stock_code, task_id)
            await db.commit()

            # 1. 回填 K 线（多取数据保证 MA60 有足够历史）
            klines = await fetcher.fetch_daily_kline(stock_code, market=market, days=days)
            if not klines:
                raise ValueError(f"[{stock_code}] 未获取到 K 线数据")
            saved = await save_klines(db, stock_code, klines)
            if saved <= 0:
                raise ValueError(f"[{stock_code}] K 线写入 0 条")
            await db.commit()
            logger.info(f"[{stock_code}] 回填 K 线 {saved} 条")

            # 2. 立即计算技术指标（MA / MACD / RSI / KDJ / 布林带）
            try:
                analyzer = TechnicalAnalyzer()
                ind_saved = await analyzer.calc_and_save(db, stock_code)
                await update_volume_ratios(db, stock_code)
                await db.commit()
                logger.info(f"[{stock_code}] 技术指标计算完成，写入 {ind_saved} 条")
            except Exception as e:
                logger.error(f"[{stock_code}] 技术指标计算失败: {e}")
                await db.rollback()

            # 3. 基本面数据
            fundamental = await fetcher.fetch_fundamental(stock_code, market=market)
            if fundamental:
                await save_fundamental(db, stock_code, fundamental)
                await db.commit()
                logger.info(f"[{stock_code}] 基本面数据写入完成")

            # 3.5 实时行情缓存：让首页表格添加后尽快有 current_price，失败不影响历史数据。
            try:
                from app.services.quote_cache import update_quote_cache
                quotes = await fetcher.fetch_realtime_quotes([stock_code])
                if quotes:
                    await update_quote_cache(quotes)
                    logger.info(f"[{stock_code}] 实时行情缓存写入完成")
            except Exception as e:
                logger.warning(f"[{stock_code}] 实时行情缓存失败: {e}")

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
        exc_message = str(exc)

        async def _mark_failed():
            from app.core.database import AsyncSessionLocal
            from app.services.stock_service import mark_sync_failed

            async with AsyncSessionLocal() as db:
                task_id = getattr(self.request, "id", None)
                await mark_sync_failed(db, stock_code, exc_message, task_id)
                await db.commit()

        try:
            asyncio.run(_mark_failed())
        except Exception as mark_exc:
            logger.error(f"[{stock_code}] 标记同步失败状态失败: {mark_exc}")
        logger.error(f"[{stock_code}] 回填数据失败: {exc}")
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="app.tasks.data_tasks.repair_watchlist_sync_gaps")
def repair_watchlist_sync_gaps(limit: int = 20):
    """自愈扫描：发现自选股缺数据、同步卡住或失败时自动重新回填。"""

    async def _run():
        from datetime import datetime, timedelta

        from sqlalchemy import func, select

        from app.core.database import AsyncSessionLocal
        from app.models.kline import StockDailyKline
        from app.models.stock import Stock
        from app.services.stock_service import mark_sync_pending, trigger_backfill

        now = datetime.now(UTC)
        stale_pending_cutoff = now - timedelta(minutes=10)
        stale_running_cutoff = now - timedelta(minutes=20)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    Stock,
                    func.count(StockDailyKline.id).label("kline_rows"),
                    func.max(StockDailyKline.trade_date).label("last_kline"),
                )
                .outerjoin(StockDailyKline, StockDailyKline.stock_id == Stock.id)
                .where(Stock.is_watchlist.is_(True))
                .group_by(Stock.id)
                .order_by(Stock.id)
            )
            scanned = 0
            candidates: list[tuple[Stock, str]] = []
            for stock, kline_rows, _last_kline in result.all():
                scanned += 1
                status = stock.sync_status or ("ready" if stock.data_ready else "idle")
                started_at = stock.sync_started_at
                updated_at = stock.updated_at

                pending_stuck = status == "pending" and updated_at and updated_at < stale_pending_cutoff
                running_stuck = status == "running" and started_at and started_at < stale_running_cutoff
                failed_stale = status == "failed" and updated_at and updated_at < stale_pending_cutoff
                no_core_data = not stock.data_ready or int(kline_rows or 0) == 0

                if no_core_data and (status == "idle" or failed_stale or pending_stuck or running_stuck):
                    reason = (
                        "缺少核心行情数据"
                        if int(kline_rows or 0) == 0
                        else f"同步状态卡住: {status}"
                    )
                    if failed_stale and stock.sync_error:
                        reason = f"上次失败后重试: {stock.sync_error[:200]}"
                    candidates.append((stock, reason))
                if len(candidates) >= limit:
                    break

            queued = 0
            for stock, reason in candidates:
                task_id = trigger_backfill(stock.code, stock.market)
                await mark_sync_pending(db, stock.code, task_id)
                logger.warning(
                    f"[repair_watchlist_sync_gaps] {stock.code} 重新入队 task_id={task_id}: {reason}"
                )
                queued += 1

            await db.commit()
            return {"scanned": scanned, "queued": queued}

    return asyncio.run(_run())


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
def update_realtime_quotes(force: bool = False):
    """更新自选股实时行情。

    定时任务只在 A 股盘前/盘中/盘后短窗口运行；手动触发传 force=True，
    用于盘后或盘前刷新东方财富 spot 的最新价。
    """
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.quote_cache import update_quote_cache
        from app.services.stock_service import get_all_watchlist_codes

        if not force and not _is_quote_refresh_window():
            return

        async with AsyncSessionLocal() as db:
            codes = await get_all_watchlist_codes(db)
            if not codes:
                return
            fetcher = AKShareFetcher()
            quotes = await fetcher.fetch_realtime_quotes(codes)
            if quotes:
                await update_quote_cache(quotes)
                logger.info(f"[update_realtime_quotes] 写入 Redis 行情 {len(quotes)}/{len(codes)} 条")
            else:
                logger.warning(f"[update_realtime_quotes] 未获取到行情，codes={len(codes)}")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.refresh_watchlist_data")
def refresh_watchlist_data(days: int = 260, force: bool = False):
    """手动刷新自选股核心数据。

    用于设置页主要更新入口。不同于交易时段的 Redis 快照任务:
    - 不受交易时段限制
    - 拉取并入库日 K,确保首页/详情页有可回退行情
    - 重算技术指标、量比和 v5 目标价信号
    - 顺带刷新基本面、季度财务和盈利预测
    """

    async def _run():
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from sqlalchemy import func, select

        from app.core.database import AsyncSessionLocal
        from app.models.kline import StockDailyKline
        from app.models.stock import Stock
        from app.services.ai_analyzer.forecast_generator import (
            update_profit_forecasts as update_forecasts,
        )
        from app.services.analysis.technical_analyzer import TechnicalAnalyzer
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.fundamental_service import save_fundamental, save_quarterly_fundamentals
        from app.services.kline_service import save_klines, update_volume_ratios
        from app.services.quote_cache import update_quote_cache
        from app.services.stock_service import get_all_watchlist_codes_with_info, mark_data_ready
        from app.services.target_price_service import compute_realtime_for_stock

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)

        if not stocks:
            logger.info("[refresh_watchlist_data] 自选股为空,跳过")
            return

        if not force:
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Stock.code, func.max(StockDailyKline.trade_date))
                    .join(StockDailyKline, StockDailyKline.stock_id == Stock.id, isouter=True)
                    .where(Stock.is_watchlist.is_(True))
                    .group_by(Stock.id, Stock.code)
                )
                stale_codes = [
                    code
                    for code, last_trade_date in result.all()
                    if last_trade_date != today
                ]
            if not stale_codes:
                logger.info(
                    f"[refresh_watchlist_data] 今日 K 线已完整({len(stocks)}/{len(stocks)}),跳过重复刷新"
                )
                return {"skipped": True, "reason": "daily_kline_current", "date": today.isoformat()}

        fetcher = AKShareFetcher()
        analyzer = TechnicalAnalyzer()
        stats = {
            "stocks": len(stocks),
            "kline_rows": 0,
            "indicator_rows": 0,
            "fundamentals": 0,
            "quarterly": 0,
            "forecasts": 0,
            "v5": 0,
            "fail": 0,
        }

        quotes_by_code: dict[str, dict] = {}

        # 实时快照先尝试一次；失败不影响日 K 回填。
        try:
            a_codes = [s["code"] for s in stocks if s.get("market") == "A"]
            if a_codes:
                quotes = await fetcher.fetch_realtime_quotes(a_codes)
                if quotes:
                    quotes_by_code = {q["code"]: q for q in quotes}
                    await update_quote_cache(quotes)
                    logger.info(f"[refresh_watchlist_data] 实时行情缓存 {len(quotes)} 条")
        except Exception as e:
            logger.warning(f"[refresh_watchlist_data] 实时行情缓存失败,继续刷新日 K: {e}")

        for s in stocks:
            code = s["code"]
            market = s.get("market") or "A"
            try:
                async with AsyncSessionLocal() as db:
                    klines = await fetcher.fetch_daily_kline(code, market=market, days=days)
                    quote = quotes_by_code.get(code)
                    if market == "A" and quote:
                        quote_date = quote.get("trade_date")
                        existing_dates = {k.get("trade_date") for k in klines}
                        if quote_date and quote_date not in existing_dates and quote.get("price", 0) > 0:
                            klines.append({
                                "trade_date": quote_date,
                                "open": quote.get("open") or quote["price"],
                                "high": quote.get("high") or quote["price"],
                                "low": quote.get("low") or quote["price"],
                                "close": quote["price"],
                                "volume": quote.get("volume"),
                                "amount": quote.get("amount"),
                                "turnover": quote.get("turnover"),
                                "change_pct": quote.get("change_pct"),
                            })
                            logger.info(f"[refresh_watchlist_data][{code}] 用实时快照补今日 K 线: {quote_date}")
                    kline_saved = await save_klines(db, code, klines)
                    stats["kline_rows"] += kline_saved

                    ind_saved = await analyzer.calc_and_save(db, code)
                    stats["indicator_rows"] += ind_saved
                    await update_volume_ratios(db, code)
                    if kline_saved > 0 or ind_saved > 0:
                        await mark_data_ready(db, code)
                    await db.commit()

                    try:
                        fundamental = await fetcher.fetch_fundamental(code, market=market)
                        if fundamental:
                            await save_fundamental(db, code, fundamental)
                            stats["fundamentals"] += 1
                            await db.commit()
                    except Exception as e:
                        await db.rollback()
                        logger.warning(f"[refresh_watchlist_data][{code}] 基本面刷新失败: {e}")

                    try:
                        quarters = await fetcher.fetch_quarterly_fundamentals(
                            code, start_year="2023", market=market
                        )
                        if quarters:
                            await save_quarterly_fundamentals(db, code, quarters)
                            stats["quarterly"] += 1
                            await db.commit()
                    except Exception as e:
                        await db.rollback()
                        logger.warning(f"[refresh_watchlist_data][{code}] 季度财务刷新失败: {e}")

                    try:
                        forecast_result = await update_forecasts(db, code)
                        if forecast_result.get("rows", 0) > 0:
                            stats["forecasts"] += 1
                            await db.commit()
                    except Exception as e:
                        await db.rollback()
                        logger.warning(f"[refresh_watchlist_data][{code}] 盈利预测刷新失败: {e}")

                    try:
                        v5 = await compute_realtime_for_stock(db, s["id"])
                        if v5:
                            stats["v5"] += 1
                            await db.commit()
                    except Exception as e:
                        await db.rollback()
                        logger.warning(f"[refresh_watchlist_data][{code}] v5 信号刷新失败: {e}")
                    logger.info(
                        f"[refresh_watchlist_data][{code}] 完成: "
                        f"K线 {len(klines)} 条, 指标 {ind_saved} 条"
                    )
            except Exception as e:
                stats["fail"] += 1
                logger.error(f"[refresh_watchlist_data][{code}] 刷新失败: {e}")
            await asyncio.sleep(0.5)

        logger.info(f"[refresh_watchlist_data] 完成: {stats}")

    asyncio.run(_run())


@celery_app.task(name="app.tasks.data_tasks.update_all_fundamentals")
def update_all_fundamentals():
    """更新所有自选股基本面数据(TTM + 季度历史)"""
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.data_fetcher.akshare_fetcher import AKShareFetcher
        from app.services.fundamental_service import save_fundamental, save_quarterly_fundamentals
        from app.services.stock_service import get_all_watchlist_codes_with_info

        async with AsyncSessionLocal() as db:
            stocks = await get_all_watchlist_codes_with_info(db)
            fetcher = AKShareFetcher()
            ttm_ok = 0
            q_ok = 0
            for stock in stocks:
                code = stock["code"]
                market = stock.get("market") or "A"
                # 1) TTM 快照(原有)
                try:
                    data = await fetcher.fetch_fundamental(code, market=market)
                    await save_fundamental(db, code, data)
                    ttm_ok += 1
                except Exception as e:
                    logger.error(f"[{code}] 更新 TTM 基本面失败: {e}")

                # 2) 季度历史(新增,从 2023 起所有报告期)
                try:
                    quarters = await fetcher.fetch_quarterly_fundamentals(
                        code, start_year="2023", market=market
                    )
                    if quarters:
                        n = await save_quarterly_fundamentals(db, code, quarters)
                        q_ok += 1
                        logger.info(f"[{code}] 季度财报 {n} 期写入")
                except Exception as e:
                    logger.error(f"[{code}] 季度财报抓取失败: {e}")

                await asyncio.sleep(0.5)  # AKShare 限速

            await db.commit()
            logger.info(f"[update_all_fundamentals] TTM ok={ttm_ok}, 季度 ok={q_ok}")

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
        from app.services.ai_analyzer.forecast_generator import update_profit_forecasts as upd
        from app.services.stock_service import get_all_watchlist_codes

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
        from app.services.ai_analyzer import industry_metrics_extractor as ime
        from app.services.data_fetcher import industry_report_fetcher as irf

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


def _is_quote_refresh_window() -> bool:
    """判断当前是否在 A 股报价刷新窗口（9:00-15:30，工作日）"""
    from datetime import datetime

    import pytz

    tz = pytz.timezone("Asia/Shanghai")
    now = datetime.now(tz)

    if now.weekday() >= 5:  # 周六、周日
        return False

    from datetime import time
    t = now.time()
    return time(9, 0) <= t <= time(15, 30)


# ════════════════════════════════════════════════════════════════
# Composite tasks — 3 个用户视角的"一键操作",收敛 17 个零散 task
# ════════════════════════════════════════════════════════════════

@celery_app.task(name="app.tasks.data_tasks.refresh_all_watchlist")
def refresh_all_watchlist():
    """🔄 一键回填全 watchlist 历史数据(首次配置 / 数据全空时点)。

    内部依次触发(异步入队,不阻塞):
      - 公告补漏 + 研报元数据
      - 基本面 TTM + 一致预期
      - 北上资金 + 龙虎榜 + 财报日历
      - 业务分部 + 行业景气
      - 事件检测 + 技术指标重算
      - cninfo 公告增量
    """
    chained = [
        ("app.tasks.data_tasks.refresh_watchlist_data", []),
        ("app.tasks.news_tasks.crawl_disclosures_only", []),
        ("app.tasks.news_tasks.crawl_research_reports", []),
        ("app.tasks.data_tasks.update_capital_flows", []),
        ("app.tasks.data_tasks.update_lhb", []),
        ("app.tasks.data_tasks.sync_calendar_events", []),
        ("app.tasks.supply_chain_tasks.extract_segments_for_all", []),
        ("app.tasks.data_tasks.update_industry_metrics", []),
        ("app.tasks.analysis_tasks.calc_all_indicators", []),
        ("app.tasks.analysis_tasks.run_event_detection", []),
        ("app.tasks.news_tasks.crawl_cninfo_disclosures", []),
    ]
    for task_name, args in chained:
        celery_app.send_task(task_name, args=args)
    logger.info(f"[refresh_all_watchlist] queued {len(chained)} sub-tasks")
    return {"queued": len(chained)}


@celery_app.task(name="app.tasks.data_tasks.daily_after_close_routine")
def daily_after_close_routine():
    """🌅 每日盘后例行 — 不重新拉历史,只更新今日:行情/北上/龙虎/资讯/公告/事件。"""
    chained = [
        ("app.tasks.data_tasks.refresh_watchlist_data", []),
        ("app.tasks.data_tasks.update_capital_flows", []),
        ("app.tasks.data_tasks.update_lhb", []),
        ("app.tasks.news_tasks.crawl_disclosures_only", []),
        ("app.tasks.news_tasks.crawl_all_sources", []),
        ("app.tasks.news_tasks.crawl_cninfo_disclosures", []),
        ("app.tasks.analysis_tasks.calc_all_indicators", []),
        ("app.tasks.analysis_tasks.run_event_detection", []),
    ]
    for task_name, args in chained:
        celery_app.send_task(task_name, args=args)
    logger.info(f"[daily_after_close_routine] queued {len(chained)} sub-tasks")
    return {"queued": len(chained)}


@celery_app.task(name="app.tasks.data_tasks.monthly_universe_refresh")
def monthly_universe_refresh():
    """📊 全市场月度同步 — 全 A 股代码池 + 历史 K 线扩展 + 行业景气。"""
    chained = [
        ("app.tasks.data_tasks.sync_stock_universe", []),
        ("app.tasks.data_tasks.sync_universe_basic_data", []),
        ("app.tasks.data_tasks.update_industry_metrics", []),
    ]
    for task_name, args in chained:
        celery_app.send_task(task_name, args=args)
    logger.info(f"[monthly_universe_refresh] queued {len(chained)} sub-tasks")
    return {"queued": len(chained)}
