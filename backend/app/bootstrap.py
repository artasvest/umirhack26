"""
Создание таблиц, миграции на старте, засев админа и схемы квиза по умолчанию.
Вызывается из lifespan FastAPI и из `python -m app.bootstrap` (init-контейнер в Docker).
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.config import settings
from app.database import Base, async_session_maker, engine
from app.db_migrate import run_startup_migrations
from app.default_quiz_schema import DEFAULT_QUIZ_SCHEMA
from app.models import QuizSchemaRow, User, UserRole
from app.security import hash_password


async def run_startup_bootstrap() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_startup_migrations(engine)

    async with async_session_maker() as db:
        r = await db.execute(select(User).where(User.email == settings.ADMIN_EMAIL.strip().lower()))
        admin = r.scalar_one_or_none()
        if admin is None:
            admin = User(
                email=settings.ADMIN_EMAIL.strip().lower(),
                full_name=settings.ADMIN_NAME,
                hashed_password=hash_password(settings.ADMIN_PASSWORD),
                role=UserRole.admin,
            )
            db.add(admin)
            await db.commit()

        rc = await db.execute(select(QuizSchemaRow.id).limit(1))
        if rc.scalar_one_or_none() is None:
            db.add(QuizSchemaRow(name="default", schema=DEFAULT_QUIZ_SCHEMA, is_active=True))
            await db.commit()


def main() -> None:
    async def _run() -> None:
        try:
            await run_startup_bootstrap()
        finally:
            await engine.dispose()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
