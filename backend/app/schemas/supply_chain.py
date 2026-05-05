from pydantic import BaseModel


class SupplyChainNode(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    relation_type: str        # upstream / downstream / competitor
    company_name: str
    company_code: str | None = None
    product_desc: str | None = None
    percentage: float | None = None
    importance: str           # high / medium / low
    is_listed: bool
    data_source: str
    report_year: int | None = None


class SupplyChainRead(BaseModel):
    code: str
    name: str
    upstream: list[SupplyChainNode] = []
    downstream: list[SupplyChainNode] = []
    competitors: list[SupplyChainNode] = []
    updated_at: str | None = None


# ── 全局供应链图(聚簇分组) ─────────────────────────────────────
class SupplyChainStockMeta(BaseModel):
    """单只自选股的元数据(用于聚簇分组)"""
    code: str
    name: str
    industry: str | None = None
    market: str = "A"  # A / H


class SupplyChainEdge(BaseModel):
    """边:from_code → to_code,标注关系类型与产品描述"""
    from_code: str        # 上游公司 code(可能是非自选股的占位 code)
    to_code: str          # 下游公司 code
    from_name: str
    to_name: str
    product_desc: str | None = None
    importance: str       # high / medium / low
    relation_type: str    # upstream / downstream
    # 是否为自选股之间的连接(双向都是自选股则 True,用于高亮)
    both_listed: bool = False


class GlobalSupplyChainResponse(BaseModel):
    """全局供应链图 — 自选股 + 上下游伙伴的聚簇网络"""
    watchlist_stocks: list[SupplyChainStockMeta]   # 所有自选股
    external_companies: list[SupplyChainStockMeta] # 非自选股的上下游公司
    edges: list[SupplyChainEdge]
    industry_groups: dict[str, list[str]]          # industry -> list of codes(用于聚簇)
    stats: dict[str, int]                          # 节点/边/行业数量统计
