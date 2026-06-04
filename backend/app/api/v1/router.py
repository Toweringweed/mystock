from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis,
    analyst_reports,
    backtest,
    earnings_surprises,
    estimate_revisions,
    kline,
    news,
    research,
    settings,
    stocks,
    supply_chain,
    tags,
    target_price,
)

api_router = APIRouter()

api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(kline.router, prefix="/kline", tags=["kline"])
api_router.include_router(analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(supply_chain.router, prefix="/supply-chain", tags=["supply-chain"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
# tags 路由含 /tags 与 /stocks/{code}/tags 两个前缀，故不加 prefix
api_router.include_router(tags.router)
api_router.include_router(research.router)
# analyst_reports 含 /stocks/{code}/analyst-reports 与 /analyst-reports/recent 两个前缀,故不加 prefix
api_router.include_router(analyst_reports.router)
api_router.include_router(backtest.router)
api_router.include_router(earnings_surprises.router)
api_router.include_router(estimate_revisions.router)
api_router.include_router(target_price.router)
