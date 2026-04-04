from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.config import settings
from app.database import Base, async_session_maker, engine
from app.db_migrate import run_startup_migrations
from app.default_quiz_schema import DEFAULT_QUIZ_SCHEMA
from app.models import QuizSchemaRow, User, UserRole
from app.routers import admin_analytics, admin_quiz_schemas, analytics, auth, leads, managers, quiz_schema
from app.security import hash_password


@asynccontextmanager
async def lifespan(_: FastAPI):
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

    yield

    await engine.dispose()


app = FastAPI(title="Studio Quiz API", lifespan=lifespan)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(leads.router)
app.include_router(analytics.router)
app.include_router(admin_analytics.router)
app.include_router(admin_quiz_schemas.router)
app.include_router(managers.router)
app.include_router(quiz_schema.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
