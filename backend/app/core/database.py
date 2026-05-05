import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Celery worker 进程通过 fork 继承父进程的连接池，会导致 asyncpg event loop 错误。
# 在 Celery 进程内使用 NullPool（禁用连接池），每次任务获取全新连接。
_in_celery = os.environ.get("CELERY_WORKER_RUNNING") == "true"

engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    **({} if _in_celery else {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}),
    **({"poolclass": NullPool} if _in_celery else {}),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
