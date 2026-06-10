from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "mystock",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.data_tasks",
        "app.tasks.analysis_tasks",
        "app.tasks.news_tasks",
        "app.tasks.supply_chain_tasks",
        "app.tasks.tags_tasks",
        "app.tasks.earnings_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="celery",
    task_create_missing_queues=True,
    task_routes={
        # 手动/定时行情数据任务走独立队列，避免被 LLM/PDF 等慢任务堵住。
        "app.tasks.data_tasks.backfill_stock_data": {"queue": "data"},
        "app.tasks.data_tasks.repair_watchlist_sync_gaps": {"queue": "data"},
        "app.tasks.data_tasks.refresh_watchlist_data": {"queue": "data"},
        "app.tasks.data_tasks.update_realtime_quotes": {"queue": "data"},
        "app.tasks.data_tasks.update_all_fundamentals": {"queue": "data"},
        "app.tasks.data_tasks.update_profit_forecasts": {"queue": "data"},
        "app.tasks.data_tasks.refresh_all_watchlist": {"queue": "data"},
        "app.tasks.data_tasks.daily_after_close_routine": {"queue": "data"},
        "app.tasks.analysis_tasks.calc_all_indicators": {"queue": "data"},
    },
    # 定时任务
    beat_schedule={
        # 交易日行情更新（9:30-15:00，每15秒）
        # 实际由 data_tasks 内部判断是否在交易时段
        "update-quotes": {
            "task": "app.tasks.data_tasks.update_realtime_quotes",
            "schedule": settings.quote_update_interval_seconds,
        },
        # 每 5 分钟自愈扫描：补救新增自选股回填任务丢失、卡住或失败。
        "repair-watchlist-sync-gaps": {
            "task": "app.tasks.data_tasks.repair_watchlist_sync_gaps",
            "schedule": crontab(minute="*/5"),
        },
        # 每个交易日盘后刷新自选股核心数据（日 K + 技术指标 + 基本面 + 盈利预测 + v5）。
        # 这一步必须早于后续事件检测/日报生成，否则下游会继续使用旧 K 线。
        # Celery 配置 timezone=Asia/Shanghai；15:40 即北京时间盘后。
        "refresh-watchlist-after-close": {
            "task": "app.tasks.data_tasks.refresh_watchlist_data",
            "schedule": crontab(hour=15, minute=40, day_of_week="1-5"),
        },
        # 每日收盘后计算技术指标（16:00，作为盘后刷新失败时的轻量兜底）
        "calc-indicators-daily": {
            "task": "app.tasks.analysis_tasks.calc_all_indicators",
            "schedule": crontab(hour=16, minute=0),
        },
        # 每日 16:15：跑事件检测（技术 + 估值 + 资讯），写 stock_events
        "run-event-detection": {
            "task": "app.tasks.analysis_tasks.run_event_detection",
            "schedule": crontab(hour=16, minute=15),
        },
        # 每日 16:30：L1 Haiku 批量生成 daily_summaries，尾部检测 signal_flip
        "generate-daily-summaries": {
            "task": "app.tasks.analysis_tasks.generate_daily_summaries",
            "schedule": crontab(hour=16, minute=30),
        },
        # 每日 16:45：仅给"今日有事件"的股生成 L2 Sonnet 深度报告
        "generate-reports-for-events": {
            "task": "app.tasks.analysis_tasks.generate_reports_for_events",
            "schedule": crontab(hour=16, minute=45),
        },
        # 每整点：聚合推送 medium 级事件队列
        "dispatch-event-queue": {
            "task": "app.tasks.analysis_tasks.dispatch_event_queue",
            "schedule": crontab(minute=0),
        },
        # 资讯爬取（每3小时）
        "crawl-news": {
            "task": "app.tasks.news_tasks.crawl_all_sources",
            "schedule": crontab(minute=0, hour=f"*/{settings.news_crawl_interval_hours}"),
        },
        # 供应链智能层：同步关系实体，并把近期资讯匹配到上下游/竞品关系。
        "refresh-supply-chain-intelligence": {
            "task": "app.tasks.supply_chain_tasks.refresh_supply_chain_intelligence",
            "schedule": crontab(minute=20, hour=f"*/{settings.news_crawl_interval_hours}"),
            "args": (14,),
        },
        # 供应链覆盖率自愈：每天晚间为缺少基础上下游关系的自选股分批排队提取。
        "backfill-watchlist-supply-chains": {
            "task": "app.tasks.supply_chain_tasks.backfill_watchlist_supply_chains",
            "schedule": crontab(hour=20, minute=30),
            "kwargs": {"limit": 8, "force": False},
        },
        # 基本面数据更新（每日9:00）
        "update-fundamentals": {
            "task": "app.tasks.data_tasks.update_all_fundamentals",
            "schedule": crontab(hour=9, minute=0),
        },
        # 全量股票列表同步（每周日凌晨2:00，A股/港股代码变化不频繁）
        "sync-stock-universe": {
            "task": "app.tasks.data_tasks.sync_stock_universe",
            "schedule": crontab(hour=2, minute=0, day_of_week=0),
        },
        # 全 A 股基础数据每周同步（120 天 K 线 + 最新财报，~2.3 小时）
        # 跑在 sync-stock-universe 之后，每周日 03:00
        "sync-universe-basic-data": {
            "task": "app.tasks.data_tasks.sync_universe_basic_data",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),
        },
        # 北上资金日度（17:00，盘后东财数据已落）
        "update-capital-flows": {
            "task": "app.tasks.data_tasks.update_capital_flows",
            "schedule": crontab(hour=17, minute=0),
        },
        # 龙虎榜（17:00）
        "update-lhb": {
            "task": "app.tasks.data_tasks.update_lhb",
            "schedule": crontab(hour=17, minute=0),
        },
        # 财报日历 + 解禁日历（每周日 03:00，与股票池同步同时段）
        "sync-calendar-events": {
            "task": "app.tasks.data_tasks.sync_calendar_events",
            "schedule": crontab(hour=3, minute=0, day_of_week=0),
        },
        # 行业景气：NVDA + 4 大 CSP 最新 10-Q（每月 1 日 04:00）
        "update-industry-metrics": {
            "task": "app.tasks.data_tasks.update_industry_metrics",
            "schedule": crontab(hour=4, minute=0, day_of_month=1),
        },
        # 盈利预测刷新（同花顺一致预期 + LLM 兜底，每周日 04:30）
        "update-profit-forecasts": {
            "task": "app.tasks.data_tasks.update_profit_forecasts",
            "schedule": crontab(hour=4, minute=30, day_of_week=0),
        },
        # 财报公告专项爬取（每30分钟,AKShare 兜底)- 沪市/北交所 + 深市补漏
        "crawl-disclosures": {
            "task": "app.tasks.news_tasks.crawl_disclosures_only",
            "schedule": crontab(minute="*/30"),
        },
        # P0 升级:巨潮直连深市公告(Tier-A 5min,比 AKShare 快 6x)
        "crawl-cninfo-disclosures": {
            "task": "app.tasks.news_tasks.crawl_cninfo_disclosures",
            "schedule": crontab(minute="*/5"),
        },
        # P0 升级:消费 mystock-x-crawler 推送的 Redis 队列(Tier-A 5min)
        "consume-x-tweets": {
            "task": "app.tasks.news_tasks.consume_x_tweets",
            "schedule": crontab(minute="*/5"),
        },
        # 券商研报：每天盘前 09:15 与 盘后 16:30 各一次
        "crawl-research-morning": {
            "task": "app.tasks.news_tasks.crawl_research_reports",
            "schedule": crontab(hour=9, minute=15),
        },
        "crawl-research-evening": {
            "task": "app.tasks.news_tasks.crawl_research_reports",
            "schedule": crontab(hour=16, minute=30),
        },
        # 研报 PDF 解析 + LLM 摘要：每 5 分钟，与 process-pending-news 错开
        "process-research-pdfs": {
            "task": "app.tasks.news_tasks.process_research_pdfs",
            "schedule": crontab(minute="2-59/5"),
        },
        # 资讯流水线处理：去重/匹配/打分/分级/推送 urgent（每 5 分钟）
        "process-pending-news": {
            "task": "app.tasks.news_tasks.process_pending_news",
            "schedule": crontab(minute="*/5"),
        },
        # 重要级整点聚合推送
        "dispatch-important-summary": {
            "task": "app.tasks.news_tasks.dispatch_important_summary",
            "schedule": crontab(minute=0),
        },
        # 每日资讯摘要（8:00）
        "dispatch-daily-summary": {
            "task": "app.tasks.news_tasks.dispatch_daily_summary",
            "schedule": crontab(hour=8, minute=0),
        },
        # 财报追踪:每日盘后自动套填 earnings_surprises actual 字段(从 stock_fundamentals 季度)
        "earnings-backfill-actuals": {
            "task": "app.tasks.earnings_tasks.backfill_earnings_actuals",
            "schedule": crontab(hour=18, minute=10),
        },
        # 财报追踪:每日凌晨补算 post_release 30d 收益(等待窗口到位)
        "earnings-recompute-returns": {
            "task": "app.tasks.earnings_tasks.compute_earnings_returns",
            "schedule": crontab(hour=2, minute=30),
        },
        # 财报日历扫描:每日盘后从公告自动提取披露日期到 calendar_events
        "earnings-scan-calendar": {
            "task": "app.tasks.earnings_tasks.scan_earnings_calendar",
            "schedule": crontab(hour=18, minute=20),
        },
    },
)
