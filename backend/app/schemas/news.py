from datetime import datetime

from pydantic import BaseModel


class NewsRelatedStock(BaseModel):
    """详情页关联股票"""
    model_config = {"from_attributes": True}
    code: str
    name: str
    relevance: float


class NewsRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    summary: str | None = None
    source: str
    source_url: str | None = None
    sentiment: str | None = None   # positive / negative / neutral
    published_at: datetime | None = None
    crawled_at: datetime

    # ── Phase 1 流水线字段 ──────────────────────────────
    category: str | None = None
    direction: str | None = None       # bullish / bearish / neutral
    urgency: str | None = None         # urgent / important / info
    importance_score: float | None = None
    rule_score: float | None = None
    llm_score: float | None = None

    # ── P0 资讯升级 ────────────────────────────────────
    catalyst_type: str | None = None       # merger/earnings/regulatory/contract/sanction/research/capacity/other
    catalyst_summary: str | None = None    # L1.5 一句话(<=120 字)
    key_risks: str | None = None           # L1.5 关键风险(/分隔)
    original_title: str | None = None      # 英文资讯保留原文标题
    original_lang: str | None = None       # en/zh


class NewsDetailRead(NewsRead):
    """详情页全字段(含正文 + 关联股票)"""
    content: str | None = None
    source_authority: float | None = None
    related_stocks: list[NewsRelatedStock] = []
