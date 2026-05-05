"""股东减持/增持事件

从 insider_trades 表读取当日新增记录，触发 INSIDER_TRADE 事件。
severity 阈值：
  - 减持 ≥ 5%        → high
  - 减持 1-5%        → medium
  - 增持 ≥ 1%        → medium
  - 其他             → low（仅入库不推送）
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.insider_trade import InsiderTrade
from app.models.stock import Stock
from app.services.event_detector._helpers import upsert_event

logger = logging.getLogger(__name__)

REDUCE_HIGH_THRESHOLD = 5.0   # 减持 ≥ 5% 总股本
REDUCE_MED_THRESHOLD = 1.0
INCREASE_MED_THRESHOLD = 1.0


def _classify_severity(trade_type: str, pct_of_total: float | None) -> str:
    if pct_of_total is None:
        return "low"
    p = abs(float(pct_of_total))
    if trade_type == "reduce":
        if p >= REDUCE_HIGH_THRESHOLD:
            return "high"
        if p >= REDUCE_MED_THRESHOLD:
            return "medium"
        return "low"
    if trade_type == "increase":
        if p >= INCREASE_MED_THRESHOLD:
            return "medium"
        return "low"
    return "low"


async def detect_all(db: AsyncSession, target_date: date | None = None) -> int:
    target = target_date or date.today()
    rows = await db.execute(
        select(InsiderTrade, Stock.code, Stock.name)
        .join(Stock, Stock.id == InsiderTrade.stock_id)
        .where(InsiderTrade.ann_date == target)
    )
    created = 0
    for trade, code, name in rows.all():
        sev = _classify_severity(trade.trade_type, float(trade.pct_of_total) if trade.pct_of_total else None)
        action = "减持" if trade.trade_type == "reduce" else "增持"
        pct = float(trade.pct_of_total) if trade.pct_of_total else 0.0
        title = (
            f"{name}({code}) 股东{action} {pct:.2f}% — {trade.holder_name}"
        )
        ok = await upsert_event(
            db,
            stock_id=trade.stock_id,
            event_type="INSIDER_TRADE",
            severity=sev,
            dedup_key=f"{trade.trade_type}:{trade.holder_name}:{trade.ann_date.isoformat()}",
            title=title,
            payload={
                "trade_type": trade.trade_type,
                "holder_name": trade.holder_name,
                "ann_date": trade.ann_date.isoformat(),
                "shares": trade.shares,
                "amount": float(trade.amount) if trade.amount else None,
                "pct_of_total": pct,
                "pct_before": float(trade.pct_before) if trade.pct_before else None,
                "pct_after": float(trade.pct_after) if trade.pct_after else None,
                "price_low": float(trade.price_low) if trade.price_low else None,
                "price_high": float(trade.price_high) if trade.price_high else None,
            },
        )
        if ok:
            created += 1
    return created
