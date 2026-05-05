from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.schemas.tags import TagRead


class DivergenceRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    detected_date: date
    signal_type: str  # MACD_BULL / MACD_BEAR / RSI_BULL / RSI_BEAR
    price_point1: float | None = None
    price_point2: float | None = None
    confidence: float | None = None
    is_confirmed: bool


class ChipRead(BaseModel):
    model_config = {"from_attributes": True}

    calc_date: date
    price_ranges: list[dict]    # [{price_low, price_high, chip_pct}]
    profit_ratio: float | None = None
    avg_cost: float | None = None
    concentration: float | None = None


class ChipHistoryItem(BaseModel):
    model_config = {"from_attributes": True}

    calc_date: date
    profit_ratio: float | None = None
    avg_cost: float | None = None
    concentration: float | None = None


class FundamentalRead(BaseModel):
    """基本面汇总（含盈利预测）"""
    code: str
    name: str
    pe_ttm: float | None = None
    pe_static: float | None = None
    pb: float | None = None
    roe: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    debt_ratio: float | None = None
    current_ratio: float | None = None     # 流动比率
    cash_flow_ratio: float | None = None   # 经营现金流/净利润
    revenue_yoy: float | None = None       # 营收同比增速 %
    profit_yoy: float | None = None        # 净利润同比增速 %
    net_profit_ttm: float | None = None    # TTM净利润（亿元）
    market_cap: float | None = None        # 总市值（亿元，= PE-TTM × 净利润TTM）
    # 行业估值
    industry_pe_median: float | None = None
    pe_percentile: float | None = None     # 近5年PE百分位
    # 盈利预测
    forecasts: list["ForecastItem"] = []


class ForecastItem(BaseModel):
    model_config = {"from_attributes": True}

    forecast_year: int
    eps_forecast: float | None = None
    net_profit_forecast: float | None = None
    forward_pe: float | None = None
    analyst_count: int | None = None
    source: str


class WatchlistTableRow(BaseModel):
    """首页表格中的单行数据（按 6 维度投资分析框架组织）"""
    code: str
    name: str
    market: str
    # 维度 3 · 护城河
    gross_margin: float | None = None          # 毛利率 %
    net_margin: float | None = None            # 净利率 %
    roe: float | None = None                   # ROE %
    # 维度 4 · 动态赔率
    pe_ttm: float | None = None                # PE-TTM
    forward_pe_2026: float | None = None       # 2026 远期 PE
    forward_pe_2027: float | None = None       # 2027 远期 PE
    forecast_2026: float | None = None         # 2026 净利润预测（亿元）
    forecast_2027: float | None = None         # 2027 净利润预测（亿元）
    # 维度 5 · 业绩兑现
    revenue_yoy: float | None = None           # 营收同比 %
    profit_yoy: float | None = None            # 净利润同比 %
    # 维度 6 · 叙事窗口（来自最新 AI 报告）
    overall_signal: str | None = None          # bullish / bearish / neutral
    ai_conclusion: str | None = None           # 一句话结论
    technical_score: int | None = None         # 1~10
    fundamental_score: int | None = None       # 1~10
    technical_analysis: str | None = None      # 技术分析摘要
    industry_inflection: str | None = None     # 行业需求拐点（言简意赅）
    external_disruption: str | None = None     # 外部颠覆力量（言简意赅）
    ai_action_suggestion: str | None = None    # AI 操作建议（与用户编辑的 recommendation 区分）
    # 行情与备注
    current_price: float | None = None         # 当前价格
    ytd_change: float | None = None            # 年内涨幅 %
    recommendation: str | None = None          # 操作建议（用户可编辑）
    personal_note: str | None = None           # 个人笔记（用户自由文本）
    market_cap: float | None = None            # 总市值（亿元）
    forecast_source: str | None = None         # 预测来源：llm / manual / tushare
    tags: list["TagRead"] = []                 # 标签（主题/产业链/属性）
    # Claude「核心 + 6D + 技术」评分（2026-05 精简版:由 stock-analysis skill POST /claude-score 写入)
    claude_overall_score: float | None = None        # Tier 加权综合分（经 Veto 调整,不含核心段)
    claude_industry_score: int | None = None         # D1 行业拐点 + 上游 + 叙事(原 D1+D6 合并)
    claude_disruption_score: int | None = None       # D2 外部颠覆力量
    claude_moat_score: int | None = None             # D3 护城河变化
    claude_valuation_score: int | None = None        # D4 动态赔率
    claude_performance_score: int | None = None      # D5 业绩兑现 + 财务质量(原 D5+D7 合并)
    claude_governance_score: int | None = None       # D8 治理与资本配置
    claude_tech_score: int | None = None             # 技术评估(K 线 + 筹码 + 动量)— 新增
    claude_veto_triggered: bool | None = None
    claude_veto_reason: str | None = None
    claude_overall_label: str | None = None          # 强烈看好 / 看好 / 中性 / 看淡 / 强烈看淡
    claude_score_at: datetime | None = None

    # 财报临近预警(2026-05 新增,从 calendar_events + earnings_surprises 联合)
    upcoming_earnings_date: date | None = None        # 最近一次财报披露日(未来)
    days_to_earnings: int | None = None               # 距离披露还剩几天(< 30 触发徽章)
    last_earnings_surprise_direction: str | None = None  # 上次披露方向(beat/meet/miss)
    last_earnings_surprise_pct: float | None = None      # 上次披露净利 surprise %

    # v5 框架 — 实时目标价上行空间(2026-05 新增,主决策因子,来源 stock_target_price_realtime)
    v5_final_score: float | None = None             # 最终评分(经一致性/上调奖金 + 鲜度衰减后)
    v5_base_score: float | None = None              # 仅基于上行空间的原始 1-10 分
    v5_upside_pct: float | None = None              # 加权目标价 / 当前价 - 1, 百分比
    v5_avg_target_weighted: float | None = None     # 机构权重加权目标价
    v5_avg_target_simple: float | None = None       # 简单平均目标价
    v5_freshness_status: str | None = None          # fresh / recent / aging / stale / none
    v5_research_count_30d: int | None = None        # 近 30 天研报数
    v5_research_count_90d: int | None = None        # 近 90 天研报数
    v5_has_consensus: bool | None = None            # 是否触发一致性 +20% 奖金
    v5_upgrade_count_30d: int | None = None         # 近 30 天上调家数(≥3 触发 +40% 奖金)
    v5_veto_triggered: bool | None = None           # 是否触发否决
    v5_veto_reason: str | None = None
    v5_updated_at: datetime | None = None


class ForecastUpdate(BaseModel):
    year: int
    net_profit: float  # 亿元


class RecommendationUpdate(BaseModel):
    recommendation: str


class PersonalNoteUpdate(BaseModel):
    personal_note: str


class QuarterlyFinancialItem(BaseModel):
    """单期季度财务(用于护城河变动子卡)
    — DB 中 revenue_yi / net_profit_deducted_yi 存的是累计值(YTD),
    本 schema 增加 single_quarter_* + *_qoq 字段为后端单季 + 单季环比的计算结果
    """
    model_config = {"from_attributes": True}

    period_end: date
    period_label: str
    gross_margin: float | None = None
    roe: float | None = None
    net_margin: float | None = None
    debt_ratio: float | None = None
    revenue_yoy: float | None = None
    profit_yoy: float | None = None
    profit_qoq: float | None = None
    # 2026-05 新增 — 后端推算的单季 + 环比
    single_quarter_revenue_yi: float | None = None
    revenue_qoq: float | None = None
    single_quarter_deducted_profit_yi: float | None = None
    deducted_profit_qoq: float | None = None


class ReportRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    report_date: date
    report_type: str
    conclusion: str | None = None
    overall_signal: Literal["bullish", "bearish", "neutral"] | None = None
    technical_score: int | None = None
    fundamental_score: int | None = None
    industry_inflection: str | None = None
    external_disruption: str | None = None
    action_suggestion: str | None = None
    full_report: dict[str, Any]
    model_used: str | None = None
    generated_at: datetime


class DimSection(BaseModel):
    """单段评分 + 文字分析 + 一句话结论(2026-05 6D 框架精简版统一结构)"""
    score: int                              # 1-10 整数
    text: str                               # 100-300 字文字分析
    conclusion: str                         # ≤30 字一句话结论


class CoreSection(BaseModel):
    """核心段:目标价上行空间(主决策,不进 6D 综合分)"""
    upside_pct: float | None = None         # 加权目标价 / 当前价 - 1
    score: float | None = None              # v5 final_score(1-10)
    freshness: str | None = None            # fresh / recent / aging / stale
    text: str
    conclusion: str


class ClaudeScoreInput(BaseModel):
    """Claude「核心 + 6D + 技术」评分入参(2026-05 精简版,详见 prompts/6d_framework.md)

    框架:
    - 核心(目标价上行空间)— 独立主决策,不计入 6D 综合分
    - 6D(D1 行业拐点+叙事 / D2 外部颠覆 / D3 护城河 / D4 动态赔率 / D5 业绩+财务 / D8 治理)
    - 技术评估(K 线 + 筹码 + 60-90d 动量,含旧 D9)

    每段必须包含:score(1-10) + text(100-300 字) + conclusion(≤30 字)。

    Tier 加权综合分:
        core_avg     = mean(D3 moat, D4 valuation, D5 performance+financial)
        industry_avg = mean(D1 industry+narrative, D2 disruption)
        raw          = 0.55*core_avg + 0.30*industry_avg + 0.05*D8 + 0.10*tech
        Veto: 任一 Tier 1 ≤2 → raw = min(raw, 4.0); 非标审计 → min(raw, 3.0)
    """
    # 核心(主决策)
    core: CoreSection

    # 6D(注意:旧 D6 已并入 D1,旧 D7 已并入 D5)
    d1: DimSection                          # 行业拐点 + 上游价格弹性 + 叙事时间窗口(原 D1+D6)
    d2: DimSection                          # 外部颠覆力量(政策/地缘/技术)
    d3: DimSection                          # 护城河变化
    d4: DimSection                          # 动态赔率(估值)
    d5: DimSection                          # 业绩兑现节奏 + 财务质量(原 D5+D7)
    d8: DimSection                          # 治理与资本配置

    # 技术评估(原 narrative.technical_analysis + 规划中的 D9 动量)
    tech: DimSection

    # Veto 否决
    veto_triggered: bool = False
    veto_reason: str | None = None

    # 价位 + 内在价值(可选,与 valuation.md 对齐)
    price_levels: dict[str, float | None] | None = None
    """五档价位 dict: {heavy_buy, mid_buy, hold_low, hold_high, reduce, exit}"""
    intrinsic_value: dict[str, float | None] | None = None
    """内在价值估算 dict: {optimistic, base, pessimistic}"""

    # 综合(经 Veto 调整后)
    overall_score: float                    # Tier 加权综合分
    overall_label: Literal["强烈看好", "看好", "中性", "看淡", "强烈看淡"]
    conclusion: str                         # 全局一句话结论
    summary: str | None = None              # 可选完整摘要
    model_used: str | None = None           # 例如 "claude-opus-4-6"
