"""Идемпотентные правки схемы для существующих БД (PostgreSQL)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def run_startup_migrations(engine: AsyncEngine) -> None:
    """ADD COLUMN IF NOT EXISTS — безопасно при повторном запуске."""
    stmts = [
        "ALTER TABLE analytics_events ADD COLUMN IF NOT EXISTS quiz_schema_id INTEGER",
        "ALTER TABLE analytics_sessions ADD COLUMN IF NOT EXISTS quiz_schema_id INTEGER",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS quiz_schema_id INTEGER",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS pool_entered_at TIMESTAMPTZ",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS callback_at TIMESTAMPTZ",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS callback_note TEXT",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS ai_summary_client TEXT",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS page_url TEXT",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS utm_source VARCHAR(256)",
        "ALTER TABLE leads ADD COLUMN IF NOT EXISTS callback_due_notified BOOLEAN NOT NULL DEFAULT false",
        """
        CREATE TABLE IF NOT EXISTS telegram_link_tokens (
            token VARCHAR(64) NOT NULL PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_telegram_link_tokens_user_id ON telegram_link_tokens (user_id)",
    ]
    async with engine.begin() as conn:
        for sql in stmts:
            await conn.execute(text(sql))
        await conn.execute(
            text(
                "UPDATE leads SET pool_entered_at = created_at "
                "WHERE pool_entered_at IS NULL AND status = 'pending' "
                "AND assigned_manager_id IS NULL"
            )
        )
