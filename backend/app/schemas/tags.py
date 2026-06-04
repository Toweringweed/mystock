from typing import Literal

from pydantic import BaseModel, Field

TagCategory = Literal["theme", "industry_chain", "attribute"]


class TagRead(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    category: TagCategory
    description: str | None = None


class StockTagRead(TagRead):
    """带挂载元信息的标签视图（详情页用）"""
    source: str = "manual"           # ai / manual
    confidence: float | None = None


class StockTagAttach(BaseModel):
    """挂载请求体：name 必填；category 在创建新标签时使用"""
    name: str = Field(..., min_length=1, max_length=64)
    category: TagCategory = "theme"
    description: str | None = None
