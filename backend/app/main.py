import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings

logger = logging.getLogger(__name__)


async def _bootstrap_stock_universe():
    """应用启动时，若 stock_universe 为空则触发后台同步任务"""
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.stock_universe_service import get_universe_count

        async with AsyncSessionLocal() as db:
            count = await get_universe_count(db)

        if count == 0:
            logger.info("[Universe] 本地股票列表为空，触发后台同步任务...")
            from app.tasks.data_tasks import sync_stock_universe
            sync_stock_universe.delay()
        else:
            logger.info(f"[Universe] 本地股票列表已有 {count} 条，无需重新同步")
    except Exception as e:
        logger.warning(f"[Universe] 启动检查失败（不影响服务启动）: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：异步检查并按需同步股票列表
    asyncio.create_task(_bootstrap_stock_universe())
    yield
    # 关闭时


app = FastAPI(
    title="MyStock API",
    description="A股/港股深度分析平台",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "environment": settings.environment}
