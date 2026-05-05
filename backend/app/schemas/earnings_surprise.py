from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EarningsSurpriseInput(BaseModel):
    """单条财报预期差写入入参"""
    period_type: Literal["quarterly", "annual"]
    period: str = Field(..., max_length=16, description="如 2026Q1 / 2025")
    release_date: date
    expected_release_date: date | None = None

    # 一致预期(亿元)
    expected_revenue_yi: Decimal | None = None
    expected_net_profit_yi: Decimal | None = None
    expected_eps: Decimal | None = None
    expected_yoy_growth: Decimal | None = None
    expected_source: str | None = None

    # 实际值(亿元)
    actual_revenue_yi: Decimal | None = None
    actual_net_profit_yi: Decimal | None = None
    actual_eps: Decimal | None = None
    actual_yoy_growth: Decimal | None = None
    actual_qoq_growth: Decimal | None = None

    # Surprise(可由后端自动计算,也可由 Skill 直接传)
    surprise_revenue_pct: Decimal | None = None
    surprise_net_profit_pct: Decimal | None = None
    surprise_direction: Literal["beat", "meet", "miss"] | None = None

    # 股价反应(可由后端从 stock_daily_kline 自动算)
    price_at_release: Decimal | None = None
    pre_release_5d_return: Decimal | None = None
    pre_release_20d_return: Decimal | None = None
    post_release_1d_return: Decimal | None = None
    post_release_5d_return: Decimal | None = None
    post_release_30d_return: Decimal | None = None

    forward_eps_revision_pct: Decimal | None = None
    notes: str | None = None
    data_source: str | None = "claude_chat"


class EarningsSurpriseRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    stock_id: int
    period_type: str
    period: str
    release_date: date
    expected_release_date: date | None = None

    expected_revenue_yi: Decimal | None = None
    expected_net_profit_yi: Decimal | None = None
    expected_eps: Decimal | None = None
    expected_yoy_growth: Decimal | None = None
    expected_source: str | None = None

    actual_revenue_yi: Decimal | None = None
    actual_net_profit_yi: Decimal | None = None
    actual_eps: Decimal | None = None
    actual_yoy_growth: Decimal | None = None
    actual_qoq_growth: Decimal | None = None

    surprise_revenue_pct: Decimal | None = None
    surprise_net_profit_pct: Decimal | None = None
    surprise_direction: str | None = None

    price_at_release: Decimal | None = None
    pre_release_5d_return: Decimal | None = None
    pre_release_20d_return: Decimal | None = None
    post_release_1d_return: Decimal | None = None
    post_release_5d_return: Decimal | None = None
    post_release_30d_return: Decimal | None = None

    forward_eps_revision_pct: Decimal | None = None
    data_source: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class UpcomingEarningsItem(BaseModel):
    """即将到来的财报披露"""
    stock_id: int
    code: str
    name: str
    expected_release_date: date
    days_to_release: int
    period_hint: str | None = None  # 推断的期间(如 "2026Q2")
    last_surprise_direction: str | None = None  # 上次披露方向
    last_surprise_pct: Decimal | None = None
