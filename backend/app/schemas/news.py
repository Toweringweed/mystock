from datetime import datetime
from pydantic import BaseModel


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
