from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_messages import MANAGER_BLOCKED_MSG
from app.config import settings
from app.database import get_db
from app.models import User, UserRole

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, extra: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire, **extra}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Войдите в систему снова")
    try:
        payload = decode_token(creds.credentials)
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
        user_id = UUID(sub)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if user.role == UserRole.manager and not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MANAGER_BLOCKED_MSG)
    return user


def require_roles(*roles: UserRole):
    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
        return user

    return _dep


async def get_optional_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    if creds is None or creds.scheme.lower() != "bearer":
        return None
    try:
        payload = decode_token(creds.credentials)
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
        user_id = UUID(sub)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна")
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    if user.role == UserRole.manager and not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=MANAGER_BLOCKED_MSG)
    return user
