import asyncio
import sys
from logging.config import fileConfig

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import settings
from app.database import Base
from app import models  # noqa: F401 — регистрация моделей в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _alembic_database_url() -> str:
    """Берём URL из backend/.env (Settings). Для asyncpg без SSL на сервере — добавляем ssl=false (иначе WinError 10054)."""
    url = (settings.DATABASE_URL or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL пустой: задайте в backend/.env (как при локальном uvicorn). "
            "Для Alembic с удалённым Postgres без TLS добавьте в URL параметр ssl=false."
        )
    if "postgresql+asyncpg" in url.lower() and "ssl=" not in url.lower():
        url = f"{url}&ssl=false" if "?" in url else f"{url}?ssl=false"
    return url


config.set_main_option("sqlalchemy.url", _alembic_database_url())


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
