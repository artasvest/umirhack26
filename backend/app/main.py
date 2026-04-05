from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap import run_startup_bootstrap
from app.config import settings
from app.database import engine
from app.routers import admin_analytics, admin_quiz_schemas, analytics, auth, leads, managers, quiz_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    await run_startup_bootstrap()
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
