"""Async SQLAlchemy engine and session lifecycle management."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.database.models import Base


def _parse_url(dsn: str) -> URL:
    try:
        return make_url(dsn)
    except ArgumentError:
        raise ValueError("database_url is not a valid SQLAlchemy URL") from None


def _prepare_sqlite_directory(url: URL) -> None:
    database = url.database
    if not database or database == ":memory:":
        return
    if database.startswith("file:"):
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def ensure_database_directory(dsn: str) -> None:
    """Create the parent folder for file-backed SQLite databases."""
    url = _parse_url(dsn)
    if url.get_backend_name() == "sqlite":
        _prepare_sqlite_directory(url)


class DatabaseManager:
    """Owns the async engine and session factory for one application instance."""

    def __init__(
        self,
        dsn: str,
        *,
        echo: bool,
        pool_size: int,
        max_overflow: int,
        auto_create: bool,
    ) -> None:
        url = _parse_url(dsn)
        self._dialect = url.get_backend_name()
        self._auto_create = auto_create
        engine_kwargs: dict[str, object] = {
            "echo": echo,
            "pool_pre_ping": True,
        }

        if self._dialect == "sqlite":
            _prepare_sqlite_directory(url)
            engine_kwargs["connect_args"] = {
                "check_same_thread": False,
                "timeout": 5.0,
            }
            if not url.database or url.database == ":memory:":
                engine_kwargs["poolclass"] = StaticPool
        else:
            engine_kwargs.update(
                {
                    "pool_size": pool_size,
                    "max_overflow": max_overflow,
                    "pool_recycle": 1800,
                    "connect_args": {"timeout": 5.0},
                }
            )

        self._engine: AsyncEngine = create_async_engine(dsn, **engine_kwargs)
        self._session_factory: async_sessionmaker[AsyncSession] = (
            async_sessionmaker(
                self._engine,
                expire_on_commit=False,
                autoflush=False,
            )
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    @property
    def dialect(self) -> str:
        return self._dialect

    @property
    def auto_create(self) -> bool:
        return self._auto_create

    async def initialize(self) -> None:
        if not self._auto_create:
            return
        async with self._engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def ping(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()
