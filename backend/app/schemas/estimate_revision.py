from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class EstimateRevisionInput(BaseModel):
    revision_date: date
    forecast_year: int = Field(..., ge=2020, le=2030)

    consensus_eps: Decimal | None = None
    consensus_net_profit_yi: Decimal | None = None
    consensus_revenue_yi: Decimal | None = None
    consensus_target_price: Decimal | None = None
    institution_count: int | None = None

    # Revision % 可选,后端会从上一快照自动算
    eps_revision_pct: Decimal | None = None
    net_profit_revision_pct: Decimal | None = None
    target_price_revision_pct: Decimal | None = None
    revision_direction: Literal["up", "flat", "down"] | None = None

    source: str | None = "claude_chat"
    notes: str | None = None


class EstimateRevisionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    stock_id: int
    revision_date: date
    forecast_year: int

    consensus_eps: Decimal | None = None
    consensus_net_profit_yi: Decimal | None = None
    consensus_revenue_yi: Decimal | None = None
    consensus_target_price: Decimal | None = None
    institution_count: int | None = None

    eps_revision_pct: Decimal | None = None
    net_profit_revision_pct: Decimal | None = None
    target_price_revision_pct: Decimal | None = None
    revision_direction: str | None = None

    source: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
