from collections.abc import AsyncIterator, Iterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from megamarket.config import settings


class AsyncSessionManager:
    def __init__(self, db_url: str, *, echo: bool = False) -> None:
        self.engine = create_async_engine(
            db_url,
            echo=echo,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            autoflush=False,
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def get_session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()


class SyncSessionManager:
    def __init__(self, db_url: str, *, echo: bool = False) -> None:
        self.engine = create_engine(
            db_url,
            echo=echo,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            autoflush=False,
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def get_session(self) -> Iterator[Session]:
        with self.session_factory() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()


sync_session_manager = SyncSessionManager(
    db_url=settings.db.sync_db_url,
    echo=settings.db.db_echo,
)


async_session_manager = AsyncSessionManager(
    db_url=settings.db.async_db_url,
    echo=settings.db.db_echo,
)
