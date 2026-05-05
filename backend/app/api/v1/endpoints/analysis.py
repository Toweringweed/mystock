from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.analysis import (
    ReportRead, FundamentalRead, ChipRead, ChipHistoryItem, DivergenceRead,
    ForecastUpdate, RecommendationUpdate, PersonalNoteUpdate, ClaudeScoreInput,
    QuarterlyFinancialItem,
)

router = APIRouter()


@router.get("/{code}/report/latest", response_model=ReportRead)
async def get_latest_report(code: str, db: AsyncSession = Depends(get_db)):
    """获取最新 AI 分析报告"""
    from app.services.report_service import get_latest_report as _get
    report = await _get(db, code)
    if not report:
        raise HTTPException(status_code=404, detail="暂无分析报告")
    return report


@router.get("/{code}/report/history", response_model=list[ReportRead])
async def get_report_history(
    code: str,
    limit: int = Query(30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
):
    """获取历史分析报告"""
    from app.services.report_service import get_report_history as _get
    return await _get(db, code, limit)


@router.post("/{code}/report/refresh", status_code=202)
async def refresh_report(code: str, db: AsyncSession = Depends(get_db)):
    """手动触发重新生成分析报告"""
    from app.tasks.analysis_tasks import generate_report_task
    generate_report_task.delay(code)
    return {"message": "报告生成任务已提交"}


@router.post("/{code}/claude-score", response_model=ReportRead)
async def submit_claude_score(
    code: str,
    payload: ClaudeScoreInput,
    db: AsyncSession = Depends(get_db),
):
    """
    接收 Claude 对话综合评分并写入 analysis_reports。

    每次调用都 INSERT 一条新记录(report_type='event_driven',full_report.source='claude_chat'),
    table_service 按 generated_at DESC 取最新,即可实现"最新评分覆盖旧评分"。
    无需 UNIQUE 约束。
    """
    from datetime import date, datetime
    from sqlalchemy import select
    from app.models.stock import Stock
    from app.models.analysis import AnalysisReport

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")

    # 序列化每段 score+text+conclusion 到 dims 嵌套结构(详情页直接读)
    full_report = {
        "source": "claude_chat",
        "framework_version": "6d_tech_v1",  # 2026-05 精简版
        # 顶层 score 字段(供 table_service 快速提取,前端 watchlist 列表使用)
        "claude_industry_score": payload.d1.score,         # D1' 行业拐点+叙事(合并)
        "claude_disruption_score": payload.d2.score,       # D2 外部颠覆
        "claude_moat_score": payload.d3.score,             # D3 护城河
        "claude_valuation_score": payload.d4.score,        # D4 动态赔率
        "claude_performance_score": payload.d5.score,      # D5' 业绩+财务(合并)
        "claude_governance_score": payload.d8.score,       # D8 治理
        "claude_tech_score": payload.tech.score,           # 技术评估
        # 嵌套结构:每段完整 score + text + conclusion(详情页 + 后续分析消费)
        "core": payload.core.model_dump(),
        "dims": {
            "d1": payload.d1.model_dump(),
            "d2": payload.d2.model_dump(),
            "d3": payload.d3.model_dump(),
            "d4": payload.d4.model_dump(),
            "d5": payload.d5.model_dump(),
            "d8": payload.d8.model_dump(),
        },
        "tech": payload.tech.model_dump(),
        # Veto 状态
        "veto_triggered": payload.veto_triggered,
        "veto_reason": payload.veto_reason,
        # 价位 + 内在价值
        "price_levels": payload.price_levels,
        "intrinsic_value": payload.intrinsic_value,
        # 综合
        "claude_overall_score": payload.overall_score,
        "claude_overall_label": payload.overall_label,
        "summary": payload.summary,
    }

    report = AnalysisReport(
        stock_id=stock_id,
        report_date=date.today(),
        report_type="event_driven",
        conclusion=payload.conclusion,
        # 兼容老前端字段:technical_score = 技术段分,fundamental_score = (D3+D5')/2
        technical_score=payload.tech.score,
        fundamental_score=(payload.d3.score + payload.d5.score) // 2,
        # 顶层 D1/D2 文字写入 industry_inflection / external_disruption(向后兼容,前端 watchlist 已展示)
        industry_inflection=payload.d1.conclusion,
        external_disruption=payload.d2.conclusion,
        full_report=full_report,
        model_used=payload.model_used or "claude_chat",
        generated_at=datetime.utcnow(),
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report


@router.get("/{code}/fundamental", response_model=FundamentalRead)
async def get_fundamental(code: str, db: AsyncSession = Depends(get_db)):
    """获取基本面数据（PE、盈利预测、远期PE等）"""
    from app.services.fundamental_service import get_fundamental as _get
    return await _get(db, code)


@router.get("/{code}/chip", response_model=ChipRead)
async def get_chip(code: str, db: AsyncSession = Depends(get_db)):
    """获取筹码分布数据"""
    from app.services.chip_service import get_chip as _get
    chip = await _get(db, code)
    if not chip:
        raise HTTPException(status_code=404, detail="暂无筹码数据")
    return chip


@router.get("/{code}/chip/history", response_model=list[ChipHistoryItem])
async def get_chip_history(
    code: str,
    days: int = Query(7, ge=3, le=30),
    db: AsyncSession = Depends(get_db),
):
    """获取近 N 日筹码集中度历史"""
    from sqlalchemy import select
    from app.models.analysis import ChipDistribution
    from app.models.stock import Stock

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        return []

    rows = await db.execute(
        select(ChipDistribution)
        .where(ChipDistribution.stock_id == stock_id)
        .order_by(ChipDistribution.calc_date.desc())
        .limit(days)
    )
    return list(rows.scalars().all())


@router.get("/{code}/divergence", response_model=list[DivergenceRead])
async def get_divergence(
    code: str,
    days: int = Query(60, ge=20, le=120),
    db: AsyncSession = Depends(get_db),
):
    """获取背离信号列表"""
    from app.services.divergence_service import get_divergence as _get
    return await _get(db, code, days)


# ── 净利润预测 ────────────────────────────────────────────────────────────────

@router.post("/{code}/forecast/llm", status_code=202)
async def llm_forecast(code: str, db: AsyncSession = Depends(get_db)):
    """调用 LLM 生成/更新 2026/2027 净利润预测"""
    from app.services.ai_analyzer.forecast_generator import generate_llm_forecast
    try:
        result = await generate_llm_forecast(db, code)
        await db.commit()
        return {"message": "LLM 预测已生成", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"LLM 预测失败: {e}")


@router.put("/{code}/forecast")
async def update_forecast(
    code: str,
    payload: ForecastUpdate,
    db: AsyncSession = Depends(get_db),
):
    """手动更新某年净利润预测（亿元），以 source='manual' 写入"""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.fundamental import ProfitForecast
    from app.models.stock import Stock

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail="股票不存在")

    values = {
        "stock_id": stock_id,
        "forecast_year": payload.year,
        "net_profit_forecast": payload.net_profit * 1e8,  # 转为元
        "source": "manual",
    }
    stmt = pg_insert(ProfitForecast).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_forecast_stock_year_source",
        set_={"net_profit_forecast": stmt.excluded.net_profit_forecast},
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": "预测已更新"}


# ── 操作建议 ──────────────────────────────────────────────────────────────────

@router.get("/{code}/recommendation")
async def get_recommendation(code: str, db: AsyncSession = Depends(get_db)):
    """获取操作建议"""
    from sqlalchemy import select
    from app.models.stock import Stock
    from app.models.stock_meta import StockNote

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail="股票不存在")

    note_result = await db.execute(
        select(StockNote).where(StockNote.stock_id == stock_id)
    )
    note = note_result.scalar_one_or_none()
    return {"recommendation": note.recommendation if note else None}


@router.put("/{code}/recommendation")
async def update_recommendation(
    code: str,
    payload: RecommendationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新操作建议"""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.stock import Stock
    from app.models.stock_meta import StockNote

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail="股票不存在")

    values = {"stock_id": stock_id, "recommendation": payload.recommendation}
    stmt = pg_insert(StockNote).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={"recommendation": stmt.excluded.recommendation},
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": "建议已更新"}


@router.put("/{code}/note")
async def update_personal_note(
    code: str,
    payload: PersonalNoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新个人笔记"""
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.stock import Stock
    from app.models.stock_meta import StockNote

    result = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = result.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail="股票不存在")

    values = {"stock_id": stock_id, "personal_note": payload.personal_note}
    stmt = pg_insert(StockNote).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["stock_id"],
        set_={"personal_note": stmt.excluded.personal_note},
    )
    await db.execute(stmt)
    await db.commit()
    return {"message": "笔记已更新"}


@router.get("/{code}/quarterly-financials", response_model=list[QuarterlyFinancialItem])
async def get_quarterly_financials(
    code: str,
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """获取最近 N 期的季度财务(用于护城河变动子卡)

    DB 中 revenue_yi / net_profit_deducted_yi 是 YTD 累计:
    - Q1 累计 = Q1 单季
    - Q2 累计 = H1 = Q1 + Q2 单季 ⟹ Q2 单季 = Q2 累计 - Q1 累计
    - Q3 累计 = 9M ⟹ Q3 单季 = Q3 累计 - Q2 累计
    - Q4 累计 = 全年 ⟹ Q4 单季 = Q4 累计 - Q3 累计

    本端点返回的额外 single_quarter_* + *_qoq 字段由后端按上述规则计算。
    多取 5 期以保证最早一期 QoQ 也有上一季单季可比基准。
    """
    from sqlalchemy import select, asc
    from app.models.stock import Stock
    from app.models.backtest_infra import QuarterlyFinancialsHistory

    res = await db.execute(select(Stock.id).where(Stock.code == code))
    stock_id = res.scalar_one_or_none()
    if not stock_id:
        raise HTTPException(status_code=404, detail=f"股票 {code} 不存在")

    # 多取 5 期作 QoQ 计算缓冲(若用户请 4 期,实际拉 9 期)
    fetch_n = limit + 5
    res = await db.execute(
        select(QuarterlyFinancialsHistory)
        .where(QuarterlyFinancialsHistory.stock_id == stock_id)
        .order_by(asc(QuarterlyFinancialsHistory.period_end))
        .limit(100)
    )
    all_rows = list(res.scalars().all())
    if not all_rows:
        return []

    # 按时间升序计算单季 + QoQ
    # 索引到 quarter:同年 Q1 直接取累计;Q2/Q3/Q4 = 累计 - 上一季累计
    def parse_period(label: str) -> tuple[int, int] | None:
        # "2026Q1" -> (2026, 1)
        try:
            y = int(label[:4])
            q = int(label[5])
            return (y, q)
        except Exception:
            return None

    # 先建立 (year, q) -> row 索引
    by_yq: dict[tuple[int, int], object] = {}
    for r in all_rows:
        yq = parse_period(r.period_label)
        if yq:
            by_yq[yq] = r

    # 计算单季 + QoQ
    out = []
    sq_revenue_history: list[float | None] = []  # 时间顺序的单季营收
    sq_deducted_history: list[float | None] = []
    for r in all_rows:
        yq = parse_period(r.period_label)
        sq_rev = None
        sq_ded = None
        if yq:
            y, q = yq
            if q == 1:
                sq_rev = float(r.revenue_yi) if r.revenue_yi is not None else None
                sq_ded = float(r.net_profit_deducted_yi) if r.net_profit_deducted_yi is not None else None
            else:
                prev = by_yq.get((y, q - 1))
                if prev:
                    if r.revenue_yi is not None and prev.revenue_yi is not None:
                        sq_rev = float(r.revenue_yi) - float(prev.revenue_yi)
                    if r.net_profit_deducted_yi is not None and prev.net_profit_deducted_yi is not None:
                        sq_ded = float(r.net_profit_deducted_yi) - float(prev.net_profit_deducted_yi)

        # QoQ 基于上一季的单季值
        rev_qoq = None
        ded_qoq = None
        if sq_revenue_history and sq_revenue_history[-1] not in (None, 0):
            prev_sq_rev = sq_revenue_history[-1]
            if sq_rev is not None and prev_sq_rev:
                rev_qoq = (sq_rev / prev_sq_rev - 1) * 100
        if sq_deducted_history and sq_deducted_history[-1] not in (None, 0):
            prev_sq_ded = sq_deducted_history[-1]
            if sq_ded is not None and prev_sq_ded:
                # 注意净利可能负值,QoQ 计算用绝对值规避符号问题
                ded_qoq = (sq_ded / prev_sq_ded - 1) * 100 if prev_sq_ded > 0 else None

        sq_revenue_history.append(sq_rev)
        sq_deducted_history.append(sq_ded)

        out.append(QuarterlyFinancialItem(
            period_end=r.period_end,
            period_label=r.period_label,
            gross_margin=float(r.gross_margin) if r.gross_margin is not None else None,
            roe=float(r.roe) if r.roe is not None else None,
            net_margin=float(r.net_margin) if r.net_margin is not None else None,
            debt_ratio=float(r.debt_ratio) if r.debt_ratio is not None else None,
            revenue_yoy=float(r.revenue_yoy) if r.revenue_yoy is not None else None,
            profit_yoy=float(r.profit_yoy) if r.profit_yoy is not None else None,
            profit_qoq=float(r.profit_qoq) if r.profit_qoq is not None else None,
            single_quarter_revenue_yi=round(sq_rev, 2) if sq_rev is not None else None,
            revenue_qoq=round(rev_qoq, 2) if rev_qoq is not None else None,
            single_quarter_deducted_profit_yi=round(sq_ded, 2) if sq_ded is not None else None,
            deducted_profit_qoq=round(ded_qoq, 2) if ded_qoq is not None else None,
        ))

    # 只返回最近 limit 期(已经是 ASC,取末尾 limit 个)
    return out[-limit:]
