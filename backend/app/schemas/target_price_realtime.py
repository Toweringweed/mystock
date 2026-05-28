from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class InstitutionBreakdownItem(BaseModel):
    institution: str
    weight: float
    is_foreign: bool
    report_date: str
    rating: str | None = None
    target_price: float
    target_derived: bool = False  # True = EPS×PE 推算
    eps_y1: float | None = None
    pe_y1: float | None = None
    freshness_days: int
    source_url: str | None = None     # 研报原文 PDF / 新闻链接(展示在 breakdown 表"原文"列)


class TargetPriceRealtimeRead(BaseModel):
    model_config = {"from_attributes": True}

    stock_id: int
    current_price: Decimal | None = None
    avg_target_simple: Decimal | None = None
    avg_target_weighted: Decimal | None = None
    highest_target: Decimal | None = None
    lowest_target: Decimal | None = None
    target_dispersion_cv: Decimal | None = None
    upside_pct: Decimal | None = None
    base_score: Decimal | None = None
    final_score: Decimal | None = None
    has_consensus: bool
    bonus_consensus_pct: Decimal | None = None
    upgrade_count_30d: int
    bonus_revisions_pct: Decimal | None = None
    total_bonus_pct: Decimal | None = None
    research_count_30d: int
    research_count_90d: int
    days_since_latest: int | None = None
    freshness_status: str | None = None
    freshness_factor: Decimal | None = None
    veto_triggered: bool
    veto_reason: str | None = None
    institution_breakdown: dict[str, Any] | None = None
    updated_at: datetime
