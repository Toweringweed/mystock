from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StockSearch(BaseModel):
    code: str
    name: str
    market: Literal["A", "HK"]
    industry: str | None = None


class StockCreate(BaseModel):
    code: str
    market: Literal["A", "HK"]
    name: str | None = None  # 搜索时已知的名称，fetch_stock_info 失败时兜底


class StockRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    code: str
    market: Literal["A", "HK"]
    name: str
    industry: str | None = None
    sector: str | None = None
    is_watchlist: bool
    is_core: bool = False
    data_ready: bool
    sync_status: str = "idle"
    sync_task_id: str | None = None
    sync_error: str | None = None
    sync_started_at: datetime | None = None
    sync_completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StockCoreUpdate(BaseModel):
    """标记 / 取消核心标识"""
    is_core: bool


class QuoteRead(BaseModel):
    """实时行情（来自缓存）"""
    code: str
    name: str
    price: float
    change_pct: float
    volume: int
    amount: float
    turnover: float
    pe_ttm: float | None = None
    updated_at: str
