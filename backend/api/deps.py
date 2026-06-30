"""
FastAPI 依赖注入
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
