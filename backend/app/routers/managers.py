from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Lead, LeadStatus, User, UserRole
from app.schemas import ManagerActivePatch, ManagerCreate, ManagerStats, UserPublic
from app.security import hash_password, require_roles

router = APIRouter(prefix="/api/managers", tags=["managers"])


@router.get("", response_model=list[UserPublic])
async def list_managers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(
        select(User).where(User.role == UserRole.manager).order_by(User.created_at.desc())
    )
    users = r.scalars().all()
    return [UserPublic.model_validate(u) for u in users]


@router.post("", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def create_manager(
    body: ManagerCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    email = body.email.strip().lower()
    ex = await db.execute(select(User.id).where(User.email == email))
    if ex.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email уже занят")
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        hashed_password=hash_password(body.password),
        role=UserRole.manager,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserPublic.model_validate(user)


@router.get("/stats", response_model=list[ManagerStats])
async def managers_stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(User).where(User.role == UserRole.manager))
    managers = r.scalars().all()
    out: list[ManagerStats] = []
    for m in managers:
        ir = await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.assigned_manager_id == m.id, Lead.status == LeadStatus.in_progress)
        )
        in_progress = int(ir.scalar_one())
        cr = await db.execute(
            select(func.count())
            .select_from(Lead)
            .where(Lead.assigned_manager_id == m.id, Lead.status == LeadStatus.completed)
        )
        completed = int(cr.scalar_one())
        touched = in_progress + completed
        conv = round((completed / touched) * 100, 1) if touched else 0.0
        out.append(
            ManagerStats(
                id=m.id,
                email=m.email,
                full_name=m.full_name,
                in_progress_count=in_progress,
                completed_count=completed,
                conversion_percent=conv,
            )
        )
    return out


@router.patch("/{manager_id}", response_model=UserPublic)
async def set_manager_active(
    manager_id: UUID,
    body: ManagerActivePatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    m = await db.get(User, manager_id)
    if m is None or m.role != UserRole.manager:
        raise HTTPException(status_code=404, detail="Менеджер не найден")
    m.is_active = body.is_active
    await db.commit()
    await db.refresh(m)
    return UserPublic.model_validate(m)
