from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://aegis:aegis@localhost:5432/aegisflow")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
