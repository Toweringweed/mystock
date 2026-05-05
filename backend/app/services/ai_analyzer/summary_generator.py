"""L1 每日摘要生成器（Haiku 批量）"""
import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.daily_summary import DailySummary
from app.models.event import StockEvent
from app.models.fundamental import StockFundamental
from app.models.kline import StockDailyKline, StockTechnicalIndicator
from app.models.stock import Stock
from app.services.settings_service import get_effective_value

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MAX_TOKENS = 1500
RECENT_EVENT_DAYS = 7


@dataclass
class StockSnapshot:
    stock_id: int
    code: str
    name: str
    close: float | None
    pct_chg: float | None
    ma5: float | None
    ma20: float | None
    ma60: float | None
    rsi_14: float | None
    macd_hist: float | None
    pe_ttm: float | None
    recent_event_types: list[str]


PROMPT_TEMPLATE = """你是A股/港股资深技术分析师，下面是 {n} 只自选股的最新技术与基本面快照。请逐只快速判断当前状态，不要长篇大论。

输入：
{snapshots}

输出 JSON（无任何多余文字）：
{{
  "results": [
    {{
      "code": "股票代码",
      "label": "5字以内的标签",
      "one_liner": "一句话结论，≤80字，包含关键依据（具体指标/价位/数字）",
      "signal": "bullish|bearish|neutral"
    }}
  ]
}}

判断要点：
- label 选词具体：技术回调/突破在即/趋势走弱/震荡等待/超买回踩/底部企稳 等
- one_liner 必须给数字依据，不要套话
- signal 严格基于趋势 + 动量综合判断，不是情感倾向
"""


def _format_snapshots(snaps: list[StockSnapshot]) -> str:
    rows = []
    for s in snaps:
        ma_arr = "多头" if (s.ma5 and s.ma20 and s.ma60 and s.ma5 > s.ma20 > s.ma60) else (
            "空头" if (s.ma5 and s.ma20 and s.ma60 and s.ma5 < s.ma20 < s.ma60) else "震荡"
        )
        macd_state = "金叉区" if (s.macd_hist and s.macd_hist > 0) else "死叉区" if s.macd_hist else "—"
        rsi_state = "超买" if (s.rsi_14 and s.rsi_14 > 70) else "超卖" if (s.rsi_14 and s.rsi_14 < 30) else "中性"
        events = ",".join(s.recent_event_types) if s.recent_event_types else "无"
        rows.append(
            f"{s.code} {s.name}: 收盘{s.close} 涨跌{(s.pct_chg or 0):+.2f}% | "
            f"MA{ma_arr} | MACD{macd_state}({s.macd_hist or 0:.3f}) | "
            f"RSI14={s.rsi_14 or 0:.1f}({rsi_state}) | "
            f"PE={s.pe_ttm or 0:.1f} | 近{RECENT_EVENT_DAYS}天事件: {events}"
        )
    return "\n".join(rows)


def _parse_response(raw: str) -> list[dict]:
    if not raw:
        return []
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        return json.loads(raw[start:end]).get("results", [])
    except Exception as e:
        logger.warning(f"[summary_generator] JSON 解析失败: {e}")
        return []


class SummaryGenerator:
    async def generate_for_all(self, db: AsyncSession, summary_date: date | None = None) -> int:
        target_date = summary_date or date.today()

        snaps = await self._collect_snapshots(db, target_date)
        if not snaps:
            logger.info("[summary_generator] 无自选股数据，跳过")
            return 0

        model = "fallback-chain"  # 实际模型在 llm_client 内按 OpenRouter→OpenAI→Anthropic 选择

        # 上一日 label，用于 label_changed
        yesterday = target_date - timedelta(days=1)
        yest_rows = await db.execute(
            select(DailySummary.stock_id, DailySummary.label)
            .where(DailySummary.summary_date == yesterday)
        )
        yesterday_labels: dict[int, str | None] = {sid: lbl for sid, lbl in yest_rows.all()}

        written = 0
        for i in range(0, len(snaps), BATCH_SIZE):
            chunk = snaps[i : i + BATCH_SIZE]
            results = await self._call_llm(db, chunk)
            if not results:
                continue

            code_to_snap = {s.code: s for s in chunk}
            for r in results:
                code = str(r.get("code", "")).strip()
                snap = code_to_snap.get(code)
                if not snap:
                    continue
                label = str(r.get("label", ""))[:20] or None
                one_liner = str(r.get("one_liner", ""))[:200] or None
                sig = str(r.get("signal", "neutral"))
                yest_label = yesterday_labels.get(snap.stock_id)
                changed = bool(label and yest_label and label != yest_label)

                stmt = pg_insert(DailySummary).values(
                    stock_id=snap.stock_id,
                    summary_date=target_date,
                    label=label,
                    one_liner=one_liner,
                    signal=sig,
                    label_changed=changed,
                    model_used=model,
                    payload=r,
                ).on_conflict_do_update(
                    index_elements=["stock_id", "summary_date"],
                    set_={
                        "label": label,
                        "one_liner": one_liner,
                        "signal": sig,
                        "label_changed": changed,
                        "model_used": model,
                        "payload": r,
                    },
                )
                await db.execute(stmt)
                written += 1

        await db.flush()
        logger.info(f"[summary_generator] 写入 {written} 条 daily_summaries (date={target_date})")
        return written

    async def _collect_snapshots(
        self, db: AsyncSession, target_date: date
    ) -> list[StockSnapshot]:
        """聚合每只自选股的指标 + 基本面 + 近期事件（批量查询，避免 N+1）"""
        result = await db.execute(
            select(Stock.id, Stock.code, Stock.name)
            .where(Stock.is_watchlist.is_(True), Stock.data_ready.is_(True))
        )
        stocks = result.all()
        if not stocks:
            return []

        stock_ids = [s.id for s in stocks]

        # 批量：每只股的最新 indicator
        ind_rank = (
            select(
                StockTechnicalIndicator,
                select(StockTechnicalIndicator.id)
                .where(StockTechnicalIndicator.stock_id == StockTechnicalIndicator.stock_id)
                .order_by(StockTechnicalIndicator.trade_date.desc())
                .limit(1)
                .scalar_subquery()
                .label("latest_id"),
            )
        )
        # 上面 correlated subquery 写法在 SQLAlchemy 里不好处理，简化：用 distinct on
        from sqlalchemy import func as sa_func, and_

        ind_subq = (
            select(
                StockTechnicalIndicator.stock_id,
                sa_func.max(StockTechnicalIndicator.trade_date).label("max_date"),
            )
            .where(StockTechnicalIndicator.stock_id.in_(stock_ids))
            .group_by(StockTechnicalIndicator.stock_id)
            .subquery()
        )
        ind_rows = await db.execute(
            select(StockTechnicalIndicator)
            .join(
                ind_subq,
                and_(
                    StockTechnicalIndicator.stock_id == ind_subq.c.stock_id,
                    StockTechnicalIndicator.trade_date == ind_subq.c.max_date,
                ),
            )
        )
        ind_by_stock: dict[int, StockTechnicalIndicator] = {
            r.stock_id: r for r in ind_rows.scalars().all()
        }

        # 批量：每只股的最新 kline
        kline_subq = (
            select(
                StockDailyKline.stock_id,
                sa_func.max(StockDailyKline.trade_date).label("max_date"),
            )
            .where(StockDailyKline.stock_id.in_(stock_ids))
            .group_by(StockDailyKline.stock_id)
            .subquery()
        )
        kline_rows = await db.execute(
            select(StockDailyKline)
            .join(
                kline_subq,
                and_(
                    StockDailyKline.stock_id == kline_subq.c.stock_id,
                    StockDailyKline.trade_date == kline_subq.c.max_date,
                ),
            )
        )
        kline_by_stock: dict[int, StockDailyKline] = {
            r.stock_id: r for r in kline_rows.scalars().all()
        }

        # 批量：每只股的最新 PE-TTM
        pe_subq = (
            select(
                StockFundamental.stock_id,
                sa_func.max(StockFundamental.updated_at).label("max_t"),
            )
            .where(
                StockFundamental.stock_id.in_(stock_ids),
                StockFundamental.period_type == "ttm",
            )
            .group_by(StockFundamental.stock_id)
            .subquery()
        )
        pe_rows = await db.execute(
            select(StockFundamental.stock_id, StockFundamental.pe_ttm)
            .join(
                pe_subq,
                and_(
                    StockFundamental.stock_id == pe_subq.c.stock_id,
                    StockFundamental.updated_at == pe_subq.c.max_t,
                ),
            )
            .where(StockFundamental.period_type == "ttm")
        )
        pe_by_stock: dict[int, float | None] = {sid: pe for sid, pe in pe_rows.all()}

        # 批量：近 7 天事件类型
        event_cutoff = target_date - timedelta(days=RECENT_EVENT_DAYS)
        event_rows = await db.execute(
            select(StockEvent.stock_id, StockEvent.event_type)
            .where(StockEvent.stock_id.in_(stock_ids))
            .where(StockEvent.triggered_at >= event_cutoff)
            .distinct()
        )
        events_by_stock: dict[int, list[str]] = {}
        for sid, et in event_rows.all():
            events_by_stock.setdefault(sid, []).append(et)

        snaps: list[StockSnapshot] = []
        for s in stocks:
            ind = ind_by_stock.get(s.id)
            kline = kline_by_stock.get(s.id)
            pe_ttm = pe_by_stock.get(s.id)

            snaps.append(StockSnapshot(
                stock_id=s.id,
                code=s.code,
                name=s.name,
                close=float(kline.close) if kline and kline.close else None,
                pct_chg=float(kline.change_pct) if kline and kline.change_pct else None,
                ma5=float(ind.ma5) if ind and ind.ma5 else None,
                ma20=float(ind.ma20) if ind and ind.ma20 else None,
                ma60=float(ind.ma60) if ind and ind.ma60 else None,
                rsi_14=float(ind.rsi_14) if ind and ind.rsi_14 else None,
                macd_hist=float(ind.macd_hist) if ind and ind.macd_hist else None,
                pe_ttm=float(pe_ttm) if pe_ttm else None,
                recent_event_types=events_by_stock.get(s.id, []),
            ))
        return snaps

    async def _call_llm(self, db, snaps: list[StockSnapshot]) -> list[dict]:
        from app.services.ai_analyzer.llm_client import call_llm
        prompt = PROMPT_TEMPLATE.format(n=len(snaps), snapshots=_format_snapshots(snaps))
        try:
            raw = await call_llm(db, prompt, max_tokens=MAX_TOKENS, prefer_haiku=True)
        except Exception as e:
            logger.error(f"[summary_generator] LLM 调用失败: {e}")
            return []
        return _parse_response(raw)
