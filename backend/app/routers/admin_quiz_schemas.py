"""CRUD квизов в хранилище + активация публичной схемы."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import QuizSchemaRow, User, UserRole
from app.schemas import (
    QuizSchemaBody,
    QuizSchemaListOut,
    QuizSchemaOut,
    QuizSchemaPatch,
    QuizSchemaValidateOut,
)
from app.security import require_roles
from app.services.quiz_schema_validate import validate_quiz_schema_for_publish

router = APIRouter(prefix="/api/admin/quiz-schemas", tags=["admin-quiz-schemas"])


@router.post("/validate", response_model=QuizSchemaValidateOut)
async def validate_quiz_schema_body(
    body: QuizSchemaBody,
    _: User = Depends(require_roles(UserRole.admin)),
):
    errs = validate_quiz_schema_for_publish(body.schema)
    return QuizSchemaValidateOut(ok=len(errs) == 0, errors=errs)


@router.get("", response_model=list[QuizSchemaListOut])
async def list_quiz_schemas(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(QuizSchemaRow).order_by(QuizSchemaRow.id.desc()))
    rows = r.scalars().all()
    return [QuizSchemaListOut.model_validate(x) for x in rows]


@router.get("/{schema_id}", response_model=QuizSchemaOut)
async def get_quiz_schema(
    schema_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Квиз не найден")
    return QuizSchemaOut.model_validate(row)


@router.get("/{schema_id}/validate", response_model=QuizSchemaValidateOut)
async def validate_quiz_schema_stored(
    schema_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Квиз не найден")
    errs = validate_quiz_schema_for_publish(row.schema)
    return QuizSchemaValidateOut(ok=len(errs) == 0, errors=errs)


@router.post("", response_model=QuizSchemaOut, status_code=status.HTTP_201_CREATED)
async def create_quiz_schema(
    body: QuizSchemaBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """Новый квиз в хранилище (по умолчанию не активируется на сайте)."""
    row = QuizSchemaRow(
        name=(body.name.strip() or "Без названия")[:128],
        schema=body.schema if isinstance(body.schema, dict) else {},
        is_active=False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return QuizSchemaOut.model_validate(row)


@router.put("/{schema_id}", response_model=QuizSchemaOut)
async def update_quiz_schema(
    schema_id: int,
    body: QuizSchemaPatch,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Квиз не найден")
    if body.name is not None:
        row.name = body.name.strip()[:128] or row.name
    if body.schema is not None:
        row.schema = body.schema if isinstance(body.schema, dict) else row.schema
    await db.commit()
    await db.refresh(row)
    return QuizSchemaOut.model_validate(row)


@router.post("/{schema_id}/activate", response_model=QuizSchemaOut)
async def activate_quiz_schema(
    schema_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Квиз не найден")
    ar = await db.execute(select(QuizSchemaRow))
    for x in ar.scalars().all():
        x.is_active = False
    row.is_active = True
    await db.commit()
    await db.refresh(row)
    return QuizSchemaOut.model_validate(row)


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz_schema(
    schema_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    cr = await db.execute(select(func.count()).select_from(QuizSchemaRow))
    if int(cr.scalar_one()) <= 1:
        raise HTTPException(status_code=400, detail="Нельзя удалить единственный квиз")
    r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    row = r.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Квиз не найден")
    if row.is_active:
        raise HTTPException(status_code=400, detail="Сначала активируйте другой квиз")
    await db.execute(delete(QuizSchemaRow).where(QuizSchemaRow.id == schema_id))
    await db.commit()
    return None
