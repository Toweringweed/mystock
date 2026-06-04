"""v5 框架 — 实时目标价上行空间计算服务

主决策信号:加权目标价 + 加成(一致预期 +20% / 3 家上修 +40%)+ 时效衰减 + Veto 风控
"""
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest_infra import (
    BacktestSnapshot,
    InstitutionMetadata,
    StockDailyFactor,
)
from app.models.estimate_revision import EstimateRevision
from app.models.fundamental import ProfitForecast
from app.models.kline import StockDailyKline
from app.models.news import IndustryNews
from app.models.research import ResearchReportMeta
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
    # 优先 stock_daily_factors(含估值衍生),fallback 到 stock_daily_kline.close(原始 OHLCV)
    res = await db.execute(
        select(StockDailyFactor.close_price, StockDailyFactor.trade_date)
        .where(StockDailyFactor.stock_id == stock_id)
        .order_by(StockDailyFactor.trade_date.desc())
        .limit(1)
    )
    row = res.first()
    if row and row.close_price:
        current_price = float(row.close_price)
    else:
        res = await db.execute(
            select(StockDailyKline.close, StockDailyKline.trade_date)
            .where(StockDailyKline.stock_id == stock_id)
            .order_by(StockDailyKline.trade_date.desc())
            .limit(1)
        )
        kline_row = res.first()
        if not kline_row or not kline_row.close:
            return None
        current_price = float(kline_row.close)

    # 2) 取 30 天 / 60 天 / 90 天内的研报(用于上行空间 + 计数)
    cutoff_30d = today - timedelta(days=30)
    cutoff_60d = today - timedelta(days=60)
    cutoff_90d = today - timedelta(days=90)

    # 从 research_report_meta + industry_news 聚合 — research_report_meta 是 AKShare 抓的研报扩展表,
    # join industry_news 拿 published_at 作为 report_date。
    # research_report_meta 没有 target_price_a 字段, target_price 由 service 后续 fallback 到 eps_y1*pe_y1 推算。
    res = await db.execute(
        select(
            ResearchReportMeta.broker,
            ResearchReportMeta.rating,
            ResearchReportMeta.forecast_year_base,
            ResearchReportMeta.eps_y1, ResearchReportMeta.eps_y2, ResearchReportMeta.eps_y3,
            ResearchReportMeta.pe_y1, ResearchReportMeta.pe_y2, ResearchReportMeta.pe_y3,
            ResearchReportMeta.pdf_url,
            IndustryNews.published_at,
            IndustryNews.summary,
        )
        .join(IndustryNews, ResearchReportMeta.news_id == IndustryNews.id)
        .where(and_(
            ResearchReportMeta.stock_id == stock_id,
            IndustryNews.published_at.isnot(None),
            IndustryNews.published_at >= datetime.combine(cutoff_90d, datetime.min.time()),
        ))
        .order_by(IndustryNews.published_at.desc())
    )
    all_reports_90d = [
        SimpleNamespace(
            institution=row.broker,
            report_date=row.published_at.date(),
            rating=row.rating,
            forecast_year_base=row.forecast_year_base,
            eps_y1=row.eps_y1, eps_y2=row.eps_y2, eps_y3=row.eps_y3,
            pe_y1=row.pe_y1, pe_y2=row.pe_y2, pe_y3=row.pe_y3,
            target_price_a=None,    # research_report_meta 不含目标价,走 EPS×PE 推算
            target_price_h=None,
            net_profit_y1=None, net_profit_y2=None, net_profit_y3=None,
            is_foreign=False,
            summary=row.summary,
            source_url=row.pdf_url,
        )
        for row in res.all()
    ]

    # 去重: 同 (institution, report_date) 仅保留 1 条 — AKShare 与 web_search 经常对同一研报
    # 因 title 不同导致 content_hash 不同, 下游显示重复, 这里清理。优先目标价更新的(eps_y1*pe_y1 推算最大者)。
    _dedup_map: dict[tuple[str, date], object] = {}
    for r in all_reports_90d:
        key = (r.institution, r.report_date)
        prev = _dedup_map.get(key)
        cur_tp = float(r.eps_y1) * float(r.pe_y1) if r.eps_y1 and r.pe_y1 else 0
        prev_tp = float(prev.eps_y1) * float(prev.pe_y1) if prev and prev.eps_y1 and prev.pe_y1 else 0
        if prev is None or cur_tp > prev_tp:
            _dedup_map[key] = r
    all_reports_90d = list(_dedup_map.values())

    reports_30d = [r for r in all_reports_90d if r.report_date >= cutoff_30d]
    # 自适应加权窗口: 30 天 ≥2 篇 → 30d (优先新鲜度); 否则 60d (扩样本避免单家垄断)
    weight_window_days = 30 if len(reports_30d) >= 2 else 60
    cutoff_for_weight = cutoff_30d if weight_window_days == 30 else cutoff_60d

    if not all_reports_90d:
        # 没有任何机构覆盖 — 诚实标注
        await _upsert_realtime(db, stock_id, {
            "current_price": Decimal(str(current_price)),
            "avg_target_simple": None,
            "avg_target_weighted": None,
            "highest_target": None,
            "lowest_target": None,
            "target_dispersion_cv": None,
            "upside_pct": None,
            "base_score": None,
            "final_score": None,
            "has_consensus": False,
            "bonus_consensus_pct": Decimal("0.00"),
            "upgrade_count_30d": 0,
            "bonus_revisions_pct": Decimal("0.00"),
            "total_bonus_pct": Decimal("0.00"),
            "days_since_latest": None,
            "freshness_status": "none",
            "freshness_factor": Decimal("0.00"),
            "research_count_30d": 0,
            "research_count_90d": 0,
            "veto_triggered": False,
            "veto_reason": None,
            "institution_breakdown": {"items": [], "reason": "no_research_coverage"},
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

    # 4) 提取每条研报的目标价
    #
    # Do not derive target price from EPS × PE. In sell-side forecast tables,
    # PE is usually calculated from the report-date stock price, so EPS × PE
    # reconstructs the then-current price rather than an analyst target.
    breakdown_items = []
    target_prices_simple = []
    target_prices_weighted_num = 0.0
    target_prices_weighted_den = 0.0

    for r in all_reports_90d:
        tp = None
        derived = False
        if r.target_price_a is not None:
            tp = float(r.target_price_a)
        elif r.eps_y1 is not None and r.pe_y1 is not None and float(r.pe_y1) <= 1.5:
            # Manual target-price entries are stored as a fake EPS/PE pair:
            # eps_y1 = target_price, pe_y1 = 1.0. Keep those as explicit.
            tp = float(r.eps_y1)
        if tp is None or tp <= 0:
            continue

        meta = inst_meta.get(r.institution, {"weight": 1.0, "is_foreign": False, "type": "unknown"})
        weight = meta["weight"]

        # 自适应加权窗口:30 天 ≥2 篇用 30d, 否则用 60d (在上方 weight_window_days 决策)
        # 90 天内的所有研报仍展示在 breakdown table, 但只有 cutoff_for_weight 内的参与加权
        if r.report_date >= cutoff_for_weight:
            target_prices_simple.append(tp)
            target_prices_weighted_num += tp * weight
            target_prices_weighted_den += weight

        # 检测 fake EPS/PE: manual-add endpoint 在 target_price 无 EPS/PE 时用 (target_price, 1.0) 占位
        # pe_y1 ≈ 1.0 是 fake 标志(真实研报 PE 不会 ≤1.5),fake 行 EPS/PE 都不返回(避免前端误导)
        is_fake_eps = bool(r.pe_y1 and float(r.pe_y1) <= 1.5)
        breakdown_items.append({
            "institution": r.institution,
            "weight": round(weight, 2),
            "is_foreign": meta["is_foreign"],
            "report_date": r.report_date.isoformat(),
            "rating": r.rating,
            "target_price": round(tp, 2),
            "target_derived": derived,  # 是否 EPS×PE 推算
            "eps_y1": None if is_fake_eps else (float(r.eps_y1) if r.eps_y1 else None),
            "eps_y2": float(r.eps_y2) if getattr(r, "eps_y2", None) else None,
            "pe_y1": None if is_fake_eps else (float(r.pe_y1) if r.pe_y1 else None),
            "pe_y2": float(r.pe_y2) if getattr(r, "pe_y2", None) else None,
            "freshness_days": (today - r.report_date).days,
            "source_url": getattr(r, "source_url", None),
        })

    if not breakdown_items:
        # 有研报但都无法解析目标价
        await _upsert_realtime(db, stock_id, {
            "current_price": Decimal(str(current_price)),
            "avg_target_simple": None,
            "avg_target_weighted": None,
            "highest_target": None,
            "lowest_target": None,
            "target_dispersion_cv": None,
            "upside_pct": None,
            "base_score": None,
            "final_score": None,
            "has_consensus": False,
            "bonus_consensus_pct": Decimal("0.00"),
            "upgrade_count_30d": 0,
            "bonus_revisions_pct": Decimal("0.00"),
            "total_bonus_pct": Decimal("0.00"),
            "days_since_latest": None,
            "freshness_status": "none",
            "freshness_factor": Decimal("0.00"),
            "research_count_30d": len(reports_30d),
            "research_count_90d": len(all_reports_90d),
            "veto_triggered": False,
            "veto_reason": None,
            "institution_breakdown": {"items": [], "reason": "no_explicit_target_price"},
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

    # 5b) 研报反算加权远期 PE(用现价 / 机构 EPS 预测,过滤 fake EPS=target_price 的占位行)
    # fake 行的特征是 pe_y1 == 1.0(manual-add 占位 trick),实际 PE 几乎不会是 1.0
    fwd_pe_y1_num = 0.0
    fwd_pe_y1_den = 0.0
    fwd_pe_y2_num = 0.0
    fwd_pe_y2_den = 0.0
    for r in all_reports_90d:
        meta = inst_meta.get(r.institution, {"weight": 1.0, "is_foreign": False, "type": "unknown"})
        weight = meta["weight"]
        # y1 (2026)
        if r.eps_y1 and float(r.eps_y1) > 0 and (r.pe_y1 is None or float(r.pe_y1) > 1.5):
            fwd_pe_y1_num += (current_price / float(r.eps_y1)) * weight
            fwd_pe_y1_den += weight
        # y2 (2027)
        if getattr(r, "eps_y2", None) and float(r.eps_y2) > 0:
            fwd_pe_y2_num += (current_price / float(r.eps_y2)) * weight
            fwd_pe_y2_den += weight
    weighted_forward_pe_y1 = round(fwd_pe_y1_num / fwd_pe_y1_den, 2) if fwd_pe_y1_den > 0 else None
    weighted_forward_pe_y2 = round(fwd_pe_y2_num / fwd_pe_y2_den, 2) if fwd_pe_y2_den > 0 else None

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
            "weighted_forward_pe_y1": weighted_forward_pe_y1,
            "weighted_forward_pe_y2": weighted_forward_pe_y2,
            # 自适应加权窗口(30 或 60),前端据此显示文案
            "weight_window_days": weight_window_days,
            # 实际进入加权的研报数(去重后)
            "reports_in_weight_window": len([
                r for r in all_reports_90d if r.report_date >= cutoff_for_weight
            ]),
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
    res = await db.execute(select(Stock).where(Stock.is_watchlist))
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
