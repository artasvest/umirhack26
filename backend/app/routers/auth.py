from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_messages import MANAGER_BLOCKED_MSG
from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import LoginBody, TelegramLinkResponse, TokenResponse
from app.security import create_access_token, get_current_user, verify_password
from app.services.telegram_link import create_link_token_row

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.email == body.email.strip().lower()))
    user = r.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")
    if user.role == UserRole.manager and not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MANAGER_BLOCKED_MSG)
    token = create_access_token(
        str(user.id),
        {"role": user.role.value, "email": user.email},
    )
    return TokenResponse(
        access_token=token,
        role=user.role,
        full_name=user.full_name,
        user_id=user.id,
    )


@router.post("/telegram-link", response_model=TelegramLinkResponse)
async def create_telegram_deep_link(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role not in (UserRole.manager, UserRole.admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недоступно для этой роли")
    uname = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    if not uname:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="На сервере не задан TELEGRAM_BOT_USERNAME",
        )
    row = await create_link_token_row(db, user.id)
    url = f"https://t.me/{uname}?start={row.token}"
    return TelegramLinkResponse(url=url, expires_at=row.expires_at)
