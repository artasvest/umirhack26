"""Одноразовые токены для привязки Telegram по ссылке из кабинета на сайте."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TelegramLinkToken, User

# Параметр ?start= в t.me ограничен по длине; token_urlsafe(12) ~16 символов.
TOKEN_BYTES = 12
LINK_TTL_MINUTES = 15


def generate_link_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


async def revoke_unused_for_user(db: AsyncSession, user_id) -> None:
    await db.execute(
        delete(TelegramLinkToken).where(
            TelegramLinkToken.user_id == user_id,
            TelegramLinkToken.used_at.is_(None),
        )
    )


async def create_link_token_row(db: AsyncSession, user_id) -> TelegramLinkToken:
    await revoke_unused_for_user(db, user_id)
    now = datetime.now(timezone.utc)
    for _ in range(8):
        raw = generate_link_token()
        if len(raw) > 64:
            continue
        existing = await db.get(TelegramLinkToken, raw)
        if existing is None:
            row = TelegramLinkToken(
                token=raw,
                user_id=user_id,
                expires_at=now + timedelta(minutes=LINK_TTL_MINUTES),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row
    raise RuntimeError("Could not allocate unique telegram link token")


async def consume_telegram_link_token(db: AsyncSession, token: str, telegram_user_id_str: str) -> bool:
    if not token or len(token) > 64:
        return False
    now = datetime.now(timezone.utc)
    row = await db.get(TelegramLinkToken, token)
    if row is None or row.expires_at < now:
        return False
    if row.used_at is not None:
        return False

    user = await db.get(User, row.user_id)
    if user is None:
        return False

    if user.telegram_user_id == telegram_user_id_str:
        row.used_at = now
        await db.commit()
        return True

    r = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id_str))
    other = r.scalar_one_or_none()
    if other is not None and other.id != user.id:
        other.telegram_user_id = None

    user.telegram_user_id = telegram_user_id_str
    row.used_at = now
    await db.commit()
    return True
