from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.default_quiz_schema import DEFAULT_QUIZ_SCHEMA
from app.models import QuizSchemaRow, User, UserRole
from app.schemas import QuizSchemaBody, QuizSchemaOut
from app.security import require_roles

router = APIRouter(prefix="/api/quiz-schema", tags=["quiz-schema"])


@router.get("", response_model=QuizSchemaOut)
async def get_active_schema(db: AsyncSession = Depends(get_db)):
    r = await db.execute(
        select(QuizSchemaRow)
        .where(QuizSchemaRow.is_active.is_(True))
        .order_by(QuizSchemaRow.id.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if row is None:
        return QuizSchemaOut(id=0, name="default", schema=DEFAULT_QUIZ_SCHEMA, is_active=True)
    return QuizSchemaOut.model_validate(row)


@router.post("", response_model=QuizSchemaOut)
async def save_schema(
    body: QuizSchemaBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    ar = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.is_active.is_(True)))
    for prev in ar.scalars().all():
        prev.is_active = False
    row = QuizSchemaRow(name=body.name.strip() or "default", schema=body.schema, is_active=True)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return QuizSchemaOut.model_validate(row)
