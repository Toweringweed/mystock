from datetime import datetime

from pydantic import BaseModel


class ResearchReportRead(BaseModel):
    model_config = {"from_attributes": True}

    news_id: int
    title: str                          # 完整标题（机构：报告名称）
    broker: str
    rating: str | None = None
    published_at: datetime | None = None
    pdf_url: str | None = None

    forecast_year_base: int | None = None
    eps_y1: float | None = None
    eps_y2: float | None = None
    eps_y3: float | None = None
    pe_y1: float | None = None
    pe_y2: float | None = None
    pe_y3: float | None = None

    summary: str | None = None          # AI 摘要（100~200 字）
    content_ready: bool = False         # PDF 是否已解析（content 不为空且非占位）


class GlobalResearchReportRead(ResearchReportRead):
    """全局研报库视图，多带股票信息"""
    code: str
    stock_name: str
