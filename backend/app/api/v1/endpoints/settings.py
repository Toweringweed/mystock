"""应用设置 API"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


class SettingUpdate(BaseModel):
    key: str
    value: str


class TriggerTaskRequest(BaseModel):
    task_name: str


# 手工触发白名单：只允许 Celery 已注册的安全任务
TRIGGERABLE_TASKS: dict[str, str] = {
    # 数据采集
    "sync_stock_universe": "app.tasks.data_tasks.sync_stock_universe",
    "sync_universe_basic_data": "app.tasks.data_tasks.sync_universe_basic_data",
    "update_realtime_quotes": "app.tasks.data_tasks.update_realtime_quotes",
    "update_all_fundamentals": "app.tasks.data_tasks.update_all_fundamentals",
    "crawl_all_sources": "app.tasks.news_tasks.crawl_all_sources",
    "crawl_disclosures_only": "app.tasks.news_tasks.crawl_disclosures_only",
    "crawl_research_reports": "app.tasks.news_tasks.crawl_research_reports",
    "process_research_pdfs": "app.tasks.news_tasks.process_research_pdfs",
    # 计算
    "calc_all_indicators": "app.tasks.analysis_tasks.calc_all_indicators",
    "process_pending_news": "app.tasks.news_tasks.process_pending_news",
    # AI 分析
    "run_event_detection": "app.tasks.analysis_tasks.run_event_detection",
    "generate_daily_summaries": "app.tasks.analysis_tasks.generate_daily_summaries",
    "generate_reports_for_events": "app.tasks.analysis_tasks.generate_reports_for_events",
    # 推送
    "dispatch_event_queue": "app.tasks.analysis_tasks.dispatch_event_queue",
    "dispatch_daily_summary": "app.tasks.news_tasks.dispatch_daily_summary",
    # 资金流向 / 日历 / 行业景气
    "update_capital_flows": "app.tasks.data_tasks.update_capital_flows",
    "update_lhb": "app.tasks.data_tasks.update_lhb",
    "sync_calendar_events": "app.tasks.data_tasks.sync_calendar_events",
    "update_industry_metrics": "app.tasks.data_tasks.update_industry_metrics",
    "update_profit_forecasts": "app.tasks.data_tasks.update_profit_forecasts",
    # 业务分部(SOTP 估值)
    "extract_segments_for_all": "app.tasks.supply_chain_tasks.extract_segments_for_all",
}


@router.get("")
async def get_settings(db: AsyncSession = Depends(get_db)):
    """获取所有配置项（secret 脱敏显示）"""
    from app.services.settings_service import get_all_settings
    return await get_all_settings(db)


@router.put("")
async def update_setting(payload: SettingUpdate, db: AsyncSession = Depends(get_db)):
    """更新单个配置项"""
    from app.services.settings_service import save_setting
    try:
        await save_setting(db, payload.key, payload.value)
        await db.commit()
        return {"message": f"{payload.key} 已更新，立即生效"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/test-llm")
async def test_llm(db: AsyncSession = Depends(get_db)):
    """测试 LLM 连通性，返回可用的 provider"""
    from app.services.settings_service import get_effective_value
    from app.core.config import settings as cfg

    results = {}

    # OpenRouter
    key = await get_effective_value(db, "openrouter_api_key")
    model = await get_effective_value(db, "openrouter_model") or cfg.openrouter_model
    if key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=key, base_url="https://openrouter.ai/api/v1")
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with just 'ok'"}],
                max_tokens=5,
            )
            results["openrouter"] = {"status": "ok", "model": model, "reply": resp.choices[0].message.content}
        except Exception as e:
            results["openrouter"] = {"status": "error", "model": model, "error": str(e)}
    else:
        results["openrouter"] = {"status": "not_configured"}

    # OpenAI
    key = await get_effective_value(db, "openai_api_key")
    model = await get_effective_value(db, "openai_model") or cfg.openai_model
    if key:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=key)
            resp = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Reply with just 'ok'"}],
                max_tokens=5,
            )
            results["openai"] = {"status": "ok", "model": model, "reply": resp.choices[0].message.content}
        except Exception as e:
            results["openai"] = {"status": "error", "model": model, "error": str(e)}
    else:
        results["openai"] = {"status": "not_configured"}

    # Anthropic
    key = await get_effective_value(db, "anthropic_api_key")
    model = await get_effective_value(db, "anthropic_model") or cfg.anthropic_model
    if key:
        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=key)
            resp = await client.messages.create(
                model=model, max_tokens=5,
                messages=[{"role": "user", "content": "Reply with just 'ok'"}],
            )
            results["anthropic"] = {"status": "ok", "model": model, "reply": resp.content[0].text}
        except Exception as e:
            results["anthropic"] = {"status": "error", "model": model, "error": str(e)}
    else:
        results["anthropic"] = {"status": "not_configured"}

    return results


@router.post("/trigger-task")
async def trigger_task(payload: TriggerTaskRequest):
    """手工触发 Celery 任务（fire-and-forget）。仅白名单任务可调用。"""
    full_name = TRIGGERABLE_TASKS.get(payload.task_name)
    if not full_name:
        raise HTTPException(
            status_code=400,
            detail=f"未知任务 {payload.task_name}，可选: {list(TRIGGERABLE_TASKS.keys())}",
        )
    from app.tasks.celery_app import celery_app
    result = celery_app.send_task(full_name)
    logger.info(f"[trigger-task] {payload.task_name} → task_id={result.id}")
    return {
        "message": f"已提交任务 {payload.task_name}",
        "task_name": payload.task_name,
        "celery_task_id": result.id,
    }


@router.post("/test-notify")
async def test_notify(db: AsyncSession = Depends(get_db)):
    """发送一条测试推送到企业微信，验证 webhook 配置。"""
    from datetime import datetime, timezone
    from app.services.notifier import wechat_work_notifier
    from app.services.notifier.event_templates import format_event
    from app.services.settings_service import get_effective_value

    webhook = await get_effective_value(db, "wechat_work_webhook_url")
    if not webhook:
        raise HTTPException(status_code=400, detail="尚未配置 wechat_work_webhook_url")

    card = format_event(
        event_type="VOLUME_SPIKE",
        severity="medium",
        title=f"测试推送 · {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        payload={
            "volume": 123456,
            "avg_20": 30000,
            "ratio": 4.1,
            "change_pct": 6.8,
        },
    )
    ok = await wechat_work_notifier.send_markdown(webhook, card)
    if not ok:
        raise HTTPException(status_code=502, detail="推送失败，请检查 webhook URL 与网络")
    return {"message": "测试卡片已发送，请检查群消息"}


@router.get("/data-status")
async def data_status(db: AsyncSession = Depends(get_db)):
    """各核心表的覆盖度 + 时效快照。

    返回分组结构,前端按 group 渲染卡片。每项含:
      table       : 表名
      rows        : 总行数
      stocks      : 覆盖股票数(若适用)
      latest      : 最新数据时间(ISO)
      stale_hours : 距今小时数(供前端按阈值打"过期"标签)
      hint        : 一句话说明
    """
    from sqlalchemy import text as sql_text

    queries: list[dict] = [
        # ── 行情 ────────────────────────────
        {"group": "行情",   "table": "stock_daily_kline",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(trade_date)::text AS latest FROM stock_daily_kline",
         "hint": "日 K 线 OHLCV"},
        {"group": "行情",   "table": "stock_technical_indicators",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(trade_date)::text AS latest FROM stock_technical_indicators",
         "hint": "MA / MACD / RSI / KDJ / BOLL / 量比"},
        {"group": "行情",   "table": "divergence_signals",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(detected_date)::text AS latest FROM divergence_signals",
         "hint": "MACD/RSI 顶/底背离"},

        # ── 财务/估值 ────────────────────────
        {"group": "财务",   "table": "stock_fundamentals",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(updated_at)::text AS latest FROM stock_fundamentals",
         "hint": "PE / PB / PS / ROE / 营收 / 净利"},
        {"group": "财务",   "table": "profit_forecasts",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(updated_at)::text AS latest FROM profit_forecasts",
         "hint": "机构一致预期(同花顺,含远期 PE)"},
        {"group": "财务",   "table": "business_segments",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(created_at)::text AS latest FROM business_segments",
         "hint": "年报分部数据(SOTP 用)"},
        {"group": "财务",   "table": "supply_chains",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(updated_at)::text AS latest FROM supply_chains",
         "hint": "上游 / 下游 / 竞品"},

        # ── 资金 ────────────────────────────
        {"group": "资金",   "table": "stock_capital_flows",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(trade_date)::text AS latest FROM stock_capital_flows",
         "hint": "北上资金日度"},
        {"group": "资金",   "table": "stock_lhb",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(trade_date)::text AS latest FROM stock_lhb",
         "hint": "龙虎榜"},
        {"group": "资金",   "table": "insider_trades",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(ann_date)::text AS latest FROM insider_trades",
         "hint": "减持 / 增持(LLM 提取)"},

        # ── 事件 / 日历 ──────────────────────
        {"group": "事件",   "table": "stock_events",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(triggered_at)::text AS latest FROM stock_events",
         "hint": "事件流水(8 类)"},
        {"group": "事件",   "table": "calendar_events",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(event_date)::text AS latest FROM calendar_events",
         "hint": "财报日 / 解禁日"},

        # ── 资讯 ────────────────────────────
        {"group": "资讯",   "table": "industry_news",
         "sql": "SELECT count(*) AS rows, NULL::int AS stocks, max(published_at)::text AS latest FROM industry_news",
         "hint": "资讯主表"},
        {"group": "资讯",   "table": "news_stock_relations",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, NULL::text AS latest FROM news_stock_relations",
         "hint": "资讯-股票关联"},

        # ── AI 分析 ──────────────────────────
        {"group": "AI",     "table": "daily_summaries",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(summary_date)::text AS latest FROM daily_summaries",
         "hint": "L1 Haiku 每日摘要"},
        {"group": "AI",     "table": "analysis_reports",
         "sql": "SELECT count(*) AS rows, count(DISTINCT stock_id) AS stocks, max(report_date)::text AS latest FROM analysis_reports",
         "hint": "L2 Sonnet 深度报告"},

        # ── 行业景气 ─────────────────────────
        {"group": "行业景气", "table": "industry_metrics",
         "sql": "SELECT count(*) AS rows, NULL::int AS stocks, max(created_at)::text AS latest FROM industry_metrics",
         "hint": "NVDA 数据中心 / 4 大 CSP capex"},
    ]

    from datetime import datetime, timezone
    now = datetime.now(tz=timezone.utc)

    out = []
    for q in queries:
        try:
            row = (await db.execute(sql_text(q["sql"]))).first()
            rows = int(row.rows) if row and row.rows is not None else 0
            stocks = int(row.stocks) if row and row.stocks is not None else None
            latest = row.latest if row else None
        except Exception as e:
            logger.warning(f"data-status [{q['table']}] failed: {e}")
            rows, stocks, latest = 0, None, None

        stale_hours = None
        if latest:
            try:
                lt = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                if lt.tzinfo is None:
                    lt = lt.replace(tzinfo=timezone.utc)
                stale_hours = round((now - lt).total_seconds() / 3600, 1)
            except Exception:
                pass

        out.append({
            "group": q["group"],
            "table": q["table"],
            "rows": rows,
            "stocks": stocks,
            "latest": latest,
            "stale_hours": stale_hours,
            "hint": q["hint"],
        })
    return out


@router.post("/refresh-keywords")
async def refresh_keywords():
    """清空 Redis 中的关键词词库缓存（自选股/别名/供应链变更后调用）"""
    from app.services.news_filter import keyword_builder
    await keyword_builder.invalidate_cache()
    return {"message": "关键词缓存已清空，下次资讯流水线运行时重建"}
