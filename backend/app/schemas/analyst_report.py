from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class AnalystReportInput(BaseModel):
    """Skill / 前端写入单条研报"""
    institution: str = Field(..., max_length=64, description="机构名,如'美银证券'/'高盛'")
    is_foreign: bool = False
    report_date: date
    rating: str | None = Field(None, max_length=16, description="买入/增持/中性/减持/卖出")
    coverage_type: str | None = Field(
        None, max_length=16,
        description="initial / maintain / upgrade / downgrade",
    )
    target_price_a: Decimal | None = None  # A 股目标价(元)
    target_price_h: Decimal | None = None  # H 股目标价(港元)

    forecast_year_base: int | None = Field(None, description="预测起始年,如 2026")
    net_profit_y1: Decimal | None = None  # 亿元
    net_profit_y2: Decimal | None = None
    net_profit_y3: Decimal | None = None
    eps_y1: Decimal | None = None
    eps_y2: Decimal | None = None
    eps_y3: Decimal | None = None
    pe_y1: Decimal | None = None
    pe_y2: Decimal | None = None
    pe_y3: Decimal | None = None

    summary: str | None = None
    key_points: list[Any] | None = None
    source_url: str | None = Field(None, max_length=500)
    model_used: str | None = Field("claude_chat", max_length=32)


class AnalystReportBulkInput(BaseModel):
    reports: list[AnalystReportInput]


class AnalystReportRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    stock_id: int
    institution: str
    is_foreign: bool
    report_date: date
    rating: str | None = None
    coverage_type: str | None = None
    target_price_a: Decimal | None = None
    target_price_h: Decimal | None = None
    forecast_year_base: int | None = None
    net_profit_y1: Decimal | None = None
    net_profit_y2: Decimal | None = None
    net_profit_y3: Decimal | None = None
    eps_y1: Decimal | None = None
    eps_y2: Decimal | None = None
    eps_y3: Decimal | None = None
    pe_y1: Decimal | None = None
    pe_y2: Decimal | None = None
    pe_y3: Decimal | None = None
    summary: str | None = None
    key_points: list[Any] | None = None
    source_url: str | None = None
    model_used: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalystReportBulkResult(BaseModel):
    inserted: int
    updated: int
    reports: list[AnalystReportRead]
