"""回测 API — Claude 8D 评分 vs 后续股价表现的预测准确性分析"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.analysis import AnalysisReport
from app.models.kline import StockDailyKline
from app.models.stock import Stock

router = APIRouter()


@router.get(
    "/backtest/scores",
    tags=["backtest"],
)
async def list_score_returns(
    horizon_days: int = Query(30, ge=1, le=180, description="N 日窗口"),
    min_history_days: int = Query(0, ge=0, description="只回测分析日距今 ≥ N 天的记录(留出验证窗口)"),
    mode: str = Query(
        "prediction",
        description="prediction=评分后 N 日表现(预测验证) / lookback=评分前 N 日表现(事后印证)",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    回测数据集:每条 Claude 8D 评分记录 + 关联的 N 日股价表现。

    模式:
      - prediction(默认):评分日 → 评分日 + N 日的涨幅(预测验证,需要有未来数据)
      - lookback:评分日 - N 日 → 评分日的涨幅(事后印证,在样本量不足时使用)

    用途:
      - 散点图 X=综合分 / Y=N 日涨跌幅 — 直观看相关性
      - Spearman rank correlation:综合分排序 vs 涨跌幅排序的一致性
      - 高分股 vs 低分股的平均收益差(模型 alpha)
    """
    # 取所有 Claude 评分记录
    stmt = (
        select(AnalysisReport, Stock)
        .join(Stock, Stock.id == AnalysisReport.stock_id)
        .where(AnalysisReport.full_report["source"].astext == "claude_chat")
        .where(AnalysisReport.full_report.has_key("claude_overall_score"))
        .order_by(AnalysisReport.generated_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    today = date.today()
    cutoff_history = today - timedelta(days=min_history_days)
    items: list[dict] = []

    for ar, stock in rows:
        score_date = ar.report_date
        if score_date > cutoff_history:
            continue  # 距今不足 min_history_days,无法验证

        fr = ar.full_report or {}
        overall = fr.get("claude_overall_score")
        if overall is None:
            continue

        # 根据 mode 决定 base / target 日期
        if mode == "lookback":
            # 事后印证:base = 评分日 - N 日 / target = 评分日
            target_date = score_date
            base_anchor = score_date - timedelta(days=horizon_days)
            base_q = await db.execute(
                select(StockDailyKline.close, StockDailyKline.trade_date)
                .where(StockDailyKline.stock_id == ar.stock_id)
                .where(StockDailyKline.trade_date >= base_anchor)
                .order_by(StockDailyKline.trade_date.asc())
                .limit(1)
            )
            target_q = await db.execute(
                select(StockDailyKline.close, StockDailyKline.trade_date)
                .where(StockDailyKline.stock_id == ar.stock_id)
                .where(StockDailyKline.trade_date <= target_date)
                .order_by(StockDailyKline.trade_date.desc())
                .limit(1)
            )
        else:
            # 预测验证:base = 评分日 / target = 评分日 + N 日
            target_date = score_date + timedelta(days=horizon_days)
            base_q = await db.execute(
                select(StockDailyKline.close, StockDailyKline.trade_date)
                .where(StockDailyKline.stock_id == ar.stock_id)
                .where(StockDailyKline.trade_date >= score_date)
                .order_by(StockDailyKline.trade_date.asc())
                .limit(1)
            )
            target_q = await db.execute(
                select(StockDailyKline.close, StockDailyKline.trade_date)
                .where(StockDailyKline.stock_id == ar.stock_id)
                .where(StockDailyKline.trade_date <= target_date)
                .order_by(StockDailyKline.trade_date.desc())
                .limit(1)
            )

        base = base_q.first()
        target = target_q.first()
        if not base or not target or target.trade_date <= base.trade_date:
            continue

        try:
            base_price = float(base.close)
            target_price = float(target.close)
            return_pct = (target_price - base_price) / base_price * 100
        except (TypeError, ValueError, ZeroDivisionError):
            continue

        items.append({
            "report_id": ar.id,
            "score_at": ar.generated_at.isoformat() if isinstance(ar.generated_at, datetime) else str(ar.generated_at),
            "score_date": score_date.isoformat(),
            "code": stock.code,
            "name": stock.name,
            "claude_overall_score": overall,
            "claude_overall_label": fr.get("claude_overall_label"),
            "veto_triggered": fr.get("veto_triggered", False),
            "veto_reason": fr.get("veto_reason"),
            "industry_score": fr.get("claude_industry_score"),
            "disruption_score": fr.get("claude_disruption_score"),
            "moat_score": fr.get("claude_moat_score"),
            "valuation_score": fr.get("claude_valuation_score"),
            "performance_score": fr.get("claude_performance_score"),
            "narrative_score": fr.get("claude_narrative_score"),
            "financial_score": fr.get("claude_financial_score"),
            "governance_score": fr.get("claude_governance_score"),
            "base_date": base.trade_date.isoformat(),
            "base_price": base_price,
            "target_date": target.trade_date.isoformat(),
            "target_price": target_price,
            "return_pct": round(return_pct, 2),
            "actual_horizon_days": (target.trade_date - base.trade_date).days,
        })

    return items


@router.get(
    "/backtest/summary",
    tags=["backtest"],
)
async def get_backtest_summary(
    horizon_days: int = Query(30, ge=1, le=180),
    min_history_days: int = Query(0, ge=0),
    mode: str = Query("prediction"),
    db: AsyncSession = Depends(get_db),
):
    """汇总指标:Spearman 秩相关 / 高分组 vs 低分组平均收益 / Veto 命中率."""
    items = await list_score_returns(horizon_days, min_history_days, mode, db)
    n = len(items)
    if n == 0:
        return {
            "sample_size": 0,
            "horizon_days": horizon_days,
            "message": "no samples (try smaller min_history_days or wait for more analysis records)",
        }

    # Spearman rank correlation: 评分排序 vs 收益排序
    def _rank(values: list[float]) -> list[float]:
        sorted_idx = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        for r, idx in enumerate(sorted_idx):
            ranks[idx] = float(r + 1)
        return ranks

    scores = [it["claude_overall_score"] for it in items]
    returns = [it["return_pct"] for it in items]
    if n >= 2:
        rs, rr = _rank(scores), _rank(returns)
        mean_rs = sum(rs) / n
        mean_rr = sum(rr) / n
        cov = sum((rs[i] - mean_rs) * (rr[i] - mean_rr) for i in range(n))
        var_s = sum((r - mean_rs) ** 2 for r in rs)
        var_r = sum((r - mean_rr) ** 2 for r in rr)
        denom = (var_s * var_r) ** 0.5
        spearman = round(cov / denom, 3) if denom > 0 else None
    else:
        spearman = None

    # 高/低分组平均收益(分位数切分)
    sorted_items = sorted(items, key=lambda it: it["claude_overall_score"], reverse=True)
    top_n = max(1, n // 3)
    top_avg = sum(it["return_pct"] for it in sorted_items[:top_n]) / top_n
    bot_avg = sum(it["return_pct"] for it in sorted_items[-top_n:]) / top_n

    # Veto 命中率: Veto 触发的样本是否真的低于平均
    veto_items = [it for it in items if it["veto_triggered"]]
    non_veto_items = [it for it in items if not it["veto_triggered"]]
    veto_avg_return = (
        sum(it["return_pct"] for it in veto_items) / len(veto_items) if veto_items else None
    )
    non_veto_avg_return = (
        sum(it["return_pct"] for it in non_veto_items) / len(non_veto_items)
        if non_veto_items else None
    )

    return {
        "sample_size": n,
        "horizon_days": horizon_days,
        "min_history_days": min_history_days,
        "mode": mode,
        "spearman_rank_correlation": spearman,
        "top_third_avg_return_pct": round(top_avg, 2),
        "bottom_third_avg_return_pct": round(bot_avg, 2),
        "alpha_top_minus_bottom_pct": round(top_avg - bot_avg, 2),
        "veto_sample_count": len(veto_items),
        "non_veto_sample_count": len(non_veto_items),
        "veto_avg_return_pct": round(veto_avg_return, 2) if veto_avg_return is not None else None,
        "non_veto_avg_return_pct": round(non_veto_avg_return, 2) if non_veto_avg_return is not None else None,
    }
