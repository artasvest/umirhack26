import asyncio
import sys
from logging.config import fileConfig
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, create_async_engine

from alembic import context

from app.config import settings
from app.database import Base
from app import models  # noqa: F401 — регистрация моделей в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _alembic_database_url() -> str:
    """URL из backend/.env. Убираем ssl/sslmode из query — asyncpg.connect() не принимает sslmode как kwarg из URL."""
    url = (settings.DATABASE_URL or "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL пустой: задайте в backend/.env (как при локальном uvicorn)."
        )
    if "postgresql+asyncpg" not in url.lower():
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("ssl", None)
    qs.pop("sslmode", None)
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


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
    url = config.get_main_option("sqlalchemy.url")
    # asyncpg не понимает sslmode= в URL (TypeError: unexpected keyword sslmode).
    # Отключаем TLS явно для типичного Postgres без SSL (Windows / удалённый сервер).
    if url.startswith("postgresql+asyncpg"):
        connectable = create_async_engine(
            url,
            poolclass=pool.NullPool,
            connect_args={"ssl": False},
        )
    else:
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


_NETWORK_HINT = """
Нет устойчивого TCP-доступа к PostgreSQL с этой машины (часто WinError 10054 /
«connection was closed in the middle»). Это не баг Alembic в коде, а сеть или настройка сервера.

Что обычно не так:
  • Порт 5432 с интернета закрыт (ufw, security group, провайдер) или Postgres слушает только 127.0.0.1.
  • Подключаться к боевой БД «в лоб» с ноутбука не обязательно: при docker compose схема поднимается при старте API (create_all + db_migrate).

Варианты:
  1) Не запускать Alembic с Windows — деплой только Docker на сервере.
  2) SSH-туннель:  ssh -L 5433:127.0.0.1:5432 user@СЕРВЕР
     В backend/.env:  DATABASE_URL=postgresql+asyncpg://USER:PASS@127.0.0.1:5433/DB
  3) Зайти по SSH на сервер и выполнить alembic из каталога backend там.
""".strip()


def _is_likely_remote_db_network_error(exc: BaseException) -> bool:
    cur: BaseException | None = exc
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        name = type(cur).__name__.lower()
        msg = str(cur).lower()
        if "10054" in str(cur) or "winerror 10054" in msg:
            return True
        if "connectionreseterror" in name or "brokenpipe" in name:
            return True
        if "connectiondoesnotexist" in name.replace("_", "") or "closed in the middle" in msg:
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def run_migrations_online() -> None:
    try:
        asyncio.run(run_async_migrations())
    except BaseException as e:
        if _is_likely_remote_db_network_error(e):
            raise RuntimeError(_NETWORK_HINT) from e
        raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
