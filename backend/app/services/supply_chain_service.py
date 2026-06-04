"""供应链数据存取服务"""
import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock import Stock
from app.models.supply_chain import SupplyChain
from app.schemas.supply_chain import (
    GlobalSupplyChainResponse,
    SupplyChainEdge,
    SupplyChainNode,
    SupplyChainRead,
    SupplyChainStockMeta,
)

logger = logging.getLogger(__name__)


async def get_supply_chain(db: AsyncSession, code: str) -> SupplyChainRead:
    result = await db.execute(
        select(Stock.id, Stock.name).where(Stock.code == code)
    )
    row = result.first()
    if not row:
        return SupplyChainRead(code=code, name=code)

    stock_id, name = row.id, row.name

    sc_result = await db.execute(
        select(SupplyChain)
        .where(SupplyChain.stock_id == stock_id)
        .order_by(SupplyChain.relation_type, SupplyChain.importance)
    )
    nodes = list(sc_result.scalars().all())

    upstream = [SupplyChainNode.model_validate(n) for n in nodes if n.relation_type == "upstream"]
    downstream = [SupplyChainNode.model_validate(n) for n in nodes if n.relation_type == "downstream"]
    competitors = [SupplyChainNode.model_validate(n) for n in nodes if n.relation_type == "competitor"]

    updated_at = nodes[0].updated_at.isoformat() if nodes else None

    return SupplyChainRead(
        code=code,
        name=name,
        upstream=upstream,
        downstream=downstream,
        competitors=competitors,
        updated_at=updated_at,
    )


async def get_global_supply_chain(db: AsyncSession) -> GlobalSupplyChainResponse:
    """聚合所有自选股的上下游 → 全局供应链图(聚簇分组)。

    - 节点:自选股(主) + 上下游公司(外部)
    - 边:relation_type=upstream/downstream,from→to 始终代表"上游→下游"流向
    - 聚簇优先级:industry > theme tag > "未分组"(实际数据中 industry 普遍未填,主要靠 theme tag)
    """
    from app.models.tag import StockTag, Tag

    # 1) 全部自选股
    res = await db.execute(
        select(Stock.id, Stock.code, Stock.name, Stock.industry, Stock.market)
        .where(Stock.is_watchlist == True)  # noqa: E712
    )
    watchlist_rows = list(res.all())
    stock_id_to_code = {r.id: r.code for r in watchlist_rows}
    code_to_name = {r.code: (r.name or r.code) for r in watchlist_rows}
    {r.code: (r.market or "A") for r in watchlist_rows}

    watchlist_codes_set = set(stock_id_to_code.values())

    # 1b) 取每只自选股的 theme 标签(用于聚簇 fallback)
    tag_res = await db.execute(
        select(StockTag.stock_id, Tag.name)
        .join(Tag, Tag.id == StockTag.tag_id)
        .where(Tag.category == "theme")
        .where(StockTag.stock_id.in_([r.id for r in watchlist_rows] or [-1]))
    )
    stock_id_to_theme_tags: dict[int, list[str]] = defaultdict(list)
    for sid, tname in tag_res.all():
        stock_id_to_theme_tags[sid].append(tname)

    # 1c) 计算每个 theme tag 的覆盖度(决定 fallback 顺序)
    tag_popularity: dict[str, int] = defaultdict(int)
    for tags in stock_id_to_theme_tags.values():
        for t in tags:
            tag_popularity[t] += 1

    def cluster_key(stock_row) -> str:
        """聚簇 key:industry > 最热门 theme tag > '未分组'"""
        if stock_row.industry:
            return stock_row.industry
        tags = stock_id_to_theme_tags.get(stock_row.id, [])
        if tags:
            # 选股票自带的所有 theme tag 中覆盖度最高的(简化:覆盖度多的更可能是行业聚簇)
            return max(tags, key=lambda t: tag_popularity[t])
        return "未分组"

    code_to_cluster = {r.code: cluster_key(r) for r in watchlist_rows}

    # 2) 全部供应链关系
    sc_res = await db.execute(
        select(SupplyChain).where(SupplyChain.relation_type.in_(["upstream", "downstream"]))
    )
    all_sc = list(sc_res.scalars().all())

    # 3) 收集外部(非自选股)公司去重
    external: dict[str, SupplyChainStockMeta] = {}
    edges: list[SupplyChainEdge] = []
    seen_edges: set[tuple[str, str, str]] = set()  # 用 (from, to, product) 去重

    for sc in all_sc:
        host_code = stock_id_to_code.get(sc.stock_id)
        if not host_code:
            continue  # host 不是自选股,跳过

        partner_code = sc.company_code or f"_ext::{sc.company_name}"
        partner_name = sc.company_name

        # 外部公司去重收集
        if partner_code not in watchlist_codes_set:
            if partner_code not in external:
                external[partner_code] = SupplyChainStockMeta(
                    code=partner_code,
                    name=partner_name,
                    industry=None,  # 外部公司行业未知
                    market="A" if sc.is_listed else "EXT",
                )

        # 边:始终上游→下游
        if sc.relation_type == "upstream":
            from_code, to_code = partner_code, host_code
            from_name, to_name = partner_name, code_to_name.get(host_code, host_code)
        else:  # downstream
            from_code, to_code = host_code, partner_code
            from_name, to_name = code_to_name.get(host_code, host_code), partner_name

        edge_key = (from_code, to_code, sc.product_desc or "")
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)

        edges.append(SupplyChainEdge(
            from_code=from_code,
            to_code=to_code,
            from_name=from_name,
            to_name=to_name,
            product_desc=sc.product_desc,
            importance=sc.importance or "medium",
            relation_type=sc.relation_type,
            both_listed=(from_code in watchlist_codes_set and to_code in watchlist_codes_set),
        ))

    # 4) 聚簇(仅自选股,外部公司不参与聚簇) — 用 cluster_key (industry > theme > 未分组)
    industry_groups: dict[str, list[str]] = defaultdict(list)
    for code, cluster in code_to_cluster.items():
        industry_groups[cluster].append(code)

    watchlist_metas = [
        SupplyChainStockMeta(
            code=r.code,
            name=r.name or r.code,
            industry=code_to_cluster.get(r.code, "未分组"),
            market=r.market or "A",
        )
        for r in watchlist_rows
    ]

    return GlobalSupplyChainResponse(
        watchlist_stocks=watchlist_metas,
        external_companies=list(external.values()),
        edges=edges,
        industry_groups=dict(industry_groups),
        stats={
            "watchlist_count": len(watchlist_metas),
            "external_count": len(external),
            "edge_count": len(edges),
            "industry_count": len(industry_groups),
            "cross_watchlist_edges": sum(1 for e in edges if e.both_listed),
        },
    )


class SupplyChainService:
    """供应链提取服务（年报 PDF → AI → 数据库）"""

    async def extract_and_save(self, db: AsyncSession, code: str) -> list[SupplyChain]:
        from sqlalchemy import delete

        from app.services.ai_analyzer.supply_chain_extractor import SupplyChainExtractor

        # 获取股票名称
        result = await db.execute(select(Stock.id, Stock.name).where(Stock.code == code))
        row = result.first()
        if not row:
            return []
        stock_id, name = row.id, row.name or code

        # 尝试获取年报文本（可选，失败不影响 AI 提取）
        text = ""
        try:
            from app.services.data_fetcher.annual_report_fetcher import AnnualReportFetcher
            fetcher = AnnualReportFetcher()
            text = await fetcher.fetch_report_text(code)
        except Exception as e:
            logger.warning(f"[{code}] 年报获取失败，使用 AI 知识库: {e}")

        # AI 提取（基于公开资料+模型知识）
        extractor = SupplyChainExtractor()
        chain_data = await extractor.extract(code, name, text, db=db)
        if not chain_data:
            logger.warning(f"[{code}] AI 未提取到供应链数据")
            return []

        # 清除旧数据后写入（全量替换）
        await db.execute(delete(SupplyChain).where(SupplyChain.stock_id == stock_id))
        saved = []
        for item in chain_data:
            node = SupplyChain(stock_id=stock_id, **item)
            db.add(node)
            saved.append(node)

        await db.flush()
        logger.info(f"[{code}] 供应链写入 {len(saved)} 条")
        return saved
