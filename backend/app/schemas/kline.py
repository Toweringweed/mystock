from datetime import date

from pydantic import BaseModel


class KlineRead(BaseModel):
    model_config = {"from_attributes": True}

    trade_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    amount: float | None = None
    turnover: float | None = None
    change_pct: float | None = None


class IndicatorRead(BaseModel):
    model_config = {"from_attributes": True}

    trade_date: date
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_hist: float | None = None
    rsi_6: float | None = None
    rsi_14: float | None = None
    rsi_24: float | None = None
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    obv: int | None = None
    # 筹码快照（从 chip_distributions 表按日期关联）
    chip_profit_ratio: float | None = None   # 获利盘比例
    chip_concentration: float | None = None  # 集中度（越小越集中）
    chip_avg_cost: float | None = None       # 平均成本
