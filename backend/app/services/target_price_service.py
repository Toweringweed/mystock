"""v5 框架 — 实时目标价上行空间计算服务

主决策信号:加权目标价 + 加成(一致预期 +20% / 3 家上修 +40%)+ 时效衰减 + Veto 风控
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analyst_report import AnalystReport
from app.models.backtest_infra import (
    BacktestSnapshot, InstitutionMetadata, QuarterlyFinancialsHistory, StockDailyFactor,
)
from app.models.estimate_revision import EstimateRevision
from app.models.fundamental import ProfitForecast
from app.models.stock import Stock
from app.models.target_price_realtime import StockTargetPriceRealtime


def upside_to_score(upside_pct: float | None) -> float:
    """上行空间 → 1-10 分"""
    if upside_pct is None:
        return 5.0
    if upside_pct > 30:
        return 10.0
    elif upside_pct > 15:
        return 8.0
    elif upside_pct > 5:
        return 6.5
    elif upside_pct > -5:
        return 5.0
    elif upside_pct > -15:
        return 3.5
    elif upside_pct > -30:
        return 2.0
    return 1.0


def freshness_factor_from_days(days: int | None) -> tuple[str, float]:
    """时效衰减系数"""
    if days is None:
        return "none", 0.0
    if days <= 7:
        return "fresh", 1.00
    if days <= 15:
        return "recent", 0.85
    if days <= 30:
        return "aging", 0.60
    return "stale", 0.30


async def compute_realtime_for_stock(db: AsyncSession, stock_id: int) -> dict[str, Any] | None:
    """计算单股实时上行空间。返回完整 breakdown 供前端展示与持久化。"""
    today = date.today()

    # 1) 当前价 — 取最近交易日收盘价
    res = await db.execute(
        select(StockDailyFactor.close_price, StockDailyFactor.trade_date)
        .where(StockDailyFactor.stock_id == stock_id)
        .order_by(StockDailyFactor.trade_date.desc())
        .limit(1)
    )
    row = res.first()
    if not row or not row.close_price:
        return None
    current_price = float(row.close_price)

    # 2) 取 30 天 / 90 天内的研报(用于上行空间 + 计数)
    cutoff_30d = today - timedelta(days=30)
    cutoff_90d = today - timedelta(days=90)

    res = await db.execute(
        select(AnalystReport)
        .where(and_(
            AnalystReport.stock_id == stock_id,
            AnalystReport.report_date >= cutoff_90d,
        ))
        .order_by(AnalystReport.report_date.desc())
    )
    all_reports_90d = list(res.scalars().all())
    reports_30d = [r for r in all_reports_90d if r.report_date >= cutoff_30d]

    if not all_reports_90d:
        # 没有任何机构覆盖 — 诚实标注
        await _upsert_realtime(db, stock_id, {
            "current_price": Decimal(str(current_price)),
            "freshness_status": "none",
            "freshness_factor": Decimal("0.00"),
            "research_count_30d": 0,
            "research_count_90d": 0,
            "veto_triggered": False,
        })
        return {
            "stock_id": stock_id,
            "current_price": current_price,
            "score": None,
            "label": "暂无机构目标价覆盖",
            "freshness_status": "none",
            "research_count_30d": 0,
            "research_count_90d": 0,
        }

    # 3) 取所有机构权重
    institution_names = list(set(r.institution for r in all_reports_90d))
    res = await db.execute(
        select(InstitutionMetadata.name, InstitutionMetadata.weight_factor,
               InstitutionMetadata.is_foreign, InstitutionMetadata.type)
        .where(InstitutionMetadata.name.in_(institution_names))
    )
    inst_meta = {
        row.name: {
            "weight": float(row.weight_factor) if row.weight_factor else 1.0,
            "is_foreign": row.is_foreign,
            "type": row.type,
        }
        for row in res.all()
    }

    # 4) 提取每条研报的目标价(优先 target_price_a,fallback eps_y1 × pe_y1)
    breakdown_items = []
    target_prices_simple = []
    target_prices_weighted_num = 0.0
    target_prices_weighted_den = 0.0

    for r in all_reports_90d:
        tp = None
        derived = False
        if r.target_price_a is not None:
            tp = float(r.target_price_a)
        elif r.eps_y1 is not None and r.pe_y1 is not None:
            try:
                tp_calc = float(r.eps_y1) * float(r.pe_y1)
                if tp_calc > 0:
                    tp = tp_calc
                    derived = True
            except Exception:
                pass
        if tp is None or tp <= 0:
            continue

        meta = inst_meta.get(r.institution, {"weight": 1.0, "is_foreign": False, "type": "unknown"})
        weight = meta["weight"]

        # 30 天内才参与加权计算(主信号)
        if r.report_date >= cutoff_30d:
            target_prices_simple.append(tp)
            target_prices_weighted_num += tp * weight
            target_prices_weighted_den += weight

        breakdown_items.append({
            "institution": r.institution,
            "weight": round(weight, 2),
            "is_foreign": meta["is_foreign"],
            "report_date": r.report_date.isoformat(),
            "rating": r.rating,
            "target_price": round(tp, 2),
            "target_derived": derived,  # 是否 EPS×PE 推算
            "eps_y1": float(r.eps_y1) if r.eps_y1 else None,
            "pe_y1": float(r.pe_y1) if r.pe_y1 else None,
            "freshness_days": (today - r.report_date).days,
        })

    if not breakdown_items:
        # 有研报但都无法解析目标价
        await _upsert_realtime(db, stock_id, {
            "current_price": Decimal(str(current_price)),
            "freshness_status": "none",
            "freshness_factor": Decimal("0.00"),
            "research_count_30d": len(reports_30d),
            "research_count_90d": len(all_reports_90d),
            "veto_triggered": False,
        })
        return {
            "stock_id": stock_id,
            "current_price": current_price,
            "score": None,
            "label": "暂无可解析的机构目标价",
        }

    # 5) 计算均值
    if target_prices_weighted_den > 0:
        avg_target_weighted = target_prices_weighted_num / target_prices_weighted_den
    else:
        avg_target_weighted = float(np.mean([item["target_price"] for item in breakdown_items]))

    avg_target_simple = float(np.mean(target_prices_simple)) if target_prices_simple else avg_target_weighted
    highest = max(item["target_price"] for item in breakdown_items)
    lowest = min(item["target_price"] for item in breakdown_items)

    # 离散度(变异系数)
    prices_list = [item["target_price"] for item in breakdown_items]
    mean_p = np.mean(prices_list)
    cv = float(np.std(prices_list) / mean_p) if mean_p > 0 else 1.0

    # 6) 上行空间(基于加权均值,与当前价比)
    upside_pct = (avg_target_weighted - current_price) / current_price * 100
    base_score = upside_to_score(upside_pct)

    # 7) 一致预期标识(展示用,不再加分:回测显示触发率 97.7%,无区分度)
    has_consensus = False
    res = await db.execute(
        select(ProfitForecast)
        .where(and_(
            ProfitForecast.stock_id == stock_id,
            ProfitForecast.forecast_year == 2026,
        ))
        .limit(5)
    )
    pf_rows = list(res.scalars().all())
    for pf in pf_rows:
        src = (pf.source or "").lower()
        if any(k in src for k in ("ths", "wind", "consensus")) and (pf.analyst_count or 0) >= 3:
            has_consensus = True
            break
    bonus_consensus = 0.0  # 2026-05 回测后移除:97.7% 样本触发,无区分度

    # 8) 加成 2:30 天内 ≥ 3 家机构上修 EPS 预测
    upgrade_count_30d = 0
    res = await db.execute(
        select(EstimateRevision)
        .where(and_(
            EstimateRevision.stock_id == stock_id,
            EstimateRevision.revision_date >= cutoff_30d,
            EstimateRevision.revision_direction == "up",
        ))
    )
    revisions = list(res.scalars().all())
    # 不同 source 算独立机构(简化:有 source 不同就算一家)
    upgrade_sources = set()
    for rev in revisions:
        if rev.source:
            upgrade_sources.add(rev.source)
    upgrade_count_30d = len(upgrade_sources)

    # 兼容:也用 analyst_reports 中 30 天内同机构 EPS 上修推断
    if upgrade_count_30d < 3:
        # 取每家机构 30 天内最新 vs 之前 30-90 天的 EPS 预测
        eps_30d = {}
        for r in reports_30d:
            if r.eps_y1:
                if r.institution not in eps_30d or r.report_date > eps_30d[r.institution][0]:
                    eps_30d[r.institution] = (r.report_date, float(r.eps_y1))
        eps_prior = {}
        cutoff_prior_low = today - timedelta(days=90)
        for r in all_reports_90d:
            if r.report_date < cutoff_30d and r.report_date >= cutoff_prior_low and r.eps_y1:
                if r.institution not in eps_prior or r.report_date > eps_prior[r.institution][0]:
                    eps_prior[r.institution] = (r.report_date, float(r.eps_y1))
        upgrade_via_revision = 0
        for inst, (_, new_eps) in eps_30d.items():
            if inst in eps_prior:
                _, old_eps = eps_prior[inst]
                if old_eps > 0 and (new_eps - old_eps) / old_eps >= 0.03:
                    upgrade_via_revision += 1
        upgrade_count_30d = max(upgrade_count_30d, upgrade_via_revision)

    bonus_revisions = 0.40 if upgrade_count_30d >= 3 else 0.0

    # 9) 总加成
    total_bonus = bonus_consensus + bonus_revisions

    # 10) 时效状态(展示用,不再做乘法衰减:回测显示 fresh/recent/aging 三组实际涨幅几乎相同,
    #     乘 0.6/0.85/1.0 反而引入跨时点噪声)
    days_since_latest = min(item["freshness_days"] for item in breakdown_items)
    freshness_status, _ = freshness_factor_from_days(days_since_latest)
    freshness_factor = 1.0  # 不再衰减,字段保留兼容性

    # 11) Veto 检查(从最新 backtest_snapshot 取 D3/D5/D7)
    veto_triggered = False
    veto_reason = None
    res = await db.execute(
        select(BacktestSnapshot.d3_moat, BacktestSnapshot.d5_performance,
               BacktestSnapshot.d7_financial)
        .where(BacktestSnapshot.stock_id == stock_id)
        .order_by(BacktestSnapshot.anchor_date.desc())
        .limit(1)
    )
    bs = res.first()
    if bs:
        if bs.d3_moat is not None and float(bs.d3_moat) <= 2:
            veto_triggered = True
            veto_reason = "D3 护城河 ≤ 2"
        elif bs.d5_performance is not None and float(bs.d5_performance) <= 2:
            veto_triggered = True
            veto_reason = "D5 业绩 ≤ 2"
        elif bs.d7_financial is not None and float(bs.d7_financial) <= 2:
            veto_triggered = True
            veto_reason = "D7 财务 ≤ 2"

    # 12) 最终分(2026-05 回测调优后):
    #     - stale(>30d 无新研报)→ final_score = None,不输出主决策信号
    #     - 否则:final_score = base_score × (1 + upgrade_bonus),Veto 触发后 ≤ 4.0
    #     - 移除 freshness_factor 乘法(无 alpha 反引入噪声)
    #     - 移除 consensus +20% 加成(触发率 97.7% 无区分度)
    if not target_prices_simple:
        # 30d 无新研报,降级为 stale 不可信,主信号置空
        freshness_status = "stale"
        final_score = None
    else:
        final_score = base_score * (1 + total_bonus)
        final_score = max(1.0, min(10.0, final_score))
        if veto_triggered:
            final_score = min(final_score, 4.0)

    # 13) 排序 breakdown(按发布日期降序,最新在前)
    breakdown_items.sort(key=lambda x: x["report_date"], reverse=True)

    # 14) Upsert
    payload = {
        "current_price": Decimal(str(round(current_price, 3))),
        "avg_target_simple": Decimal(str(round(avg_target_simple, 3))),
        "avg_target_weighted": Decimal(str(round(avg_target_weighted, 3))),
        "highest_target": Decimal(str(round(highest, 3))),
        "lowest_target": Decimal(str(round(lowest, 3))),
        "target_dispersion_cv": Decimal(str(round(cv, 4))),
        "upside_pct": Decimal(str(round(upside_pct, 2))),
        "base_score": Decimal(str(round(base_score, 2))),
        "final_score": Decimal(str(round(final_score, 2))) if final_score is not None else None,
        "has_consensus": has_consensus,
        "bonus_consensus_pct": Decimal(str(bonus_consensus)),
        "upgrade_count_30d": upgrade_count_30d,
        "bonus_revisions_pct": Decimal(str(bonus_revisions)),
        "total_bonus_pct": Decimal(str(total_bonus)),
        "research_count_30d": len(reports_30d),
        "research_count_90d": len(all_reports_90d),
        "days_since_latest": days_since_latest,
        "freshness_status": freshness_status,
        "freshness_factor": Decimal(str(freshness_factor)),
        "veto_triggered": veto_triggered,
        "veto_reason": veto_reason,
        "institution_breakdown": {
            "items": breakdown_items,
            "weighted_avg": round(avg_target_weighted, 3),
            "simple_avg": round(avg_target_simple, 3),
        },
    }
    await _upsert_realtime(db, stock_id, payload)

    return {
        "stock_id": stock_id,
        **{k: float(v) if isinstance(v, Decimal) else v for k, v in payload.items()
           if k != "institution_breakdown"},
        "institution_breakdown": payload["institution_breakdown"],
    }


async def _upsert_realtime(db: AsyncSession, stock_id: int, payload: dict):
    payload["stock_id"] = stock_id
    payload["updated_at"] = datetime.utcnow()

    stmt = pg_insert(StockTargetPriceRealtime).values(**payload)
    update_cols = {k: stmt.excluded[k] for k in payload.keys() if k != "stock_id"}
    stmt = stmt.on_conflict_do_update(index_elements=["stock_id"], set_=update_cols)
    await db.execute(stmt)
    await db.commit()


async def compute_realtime_for_all_watchlist(db: AsyncSession) -> dict[str, int]:
    """对所有自选股算实时上行空间。返回统计数据。"""
    res = await db.execute(select(Stock).where(Stock.is_watchlist == True))
    stocks = list(res.scalars().all())

    stats = {"total": len(stocks), "computed": 0, "no_target": 0, "veto": 0}
    for s in stocks:
        result = await compute_realtime_for_stock(db, s.id)
        if result is None:
            continue
        if result.get("final_score") is None:
            stats["no_target"] += 1
        else:
            stats["computed"] += 1
            if result.get("veto_triggered"):
                stats["veto"] += 1

    return stats
