import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Union
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import async_session_maker, get_db
from app.models import Lead, LeadStatus, Note, Reminder, User, UserRole
from app.schemas import (
    CallScriptResponse,
    LeadAdminPatch,
    LeadCallbackPatch,
    LeadCreate,
    LeadCreateResponse,
    LeadDetail,
    LeadListItem,
    LeadManagerDetail,
    LeadPublicView,
    LeadStatusPatch,
    NoteCreate,
    NoteOut,
    ReminderCreate,
    ReminderOut,
    SummaryPreviewBody,
    SummaryPreviewResponse,
)
from app.security import get_optional_user, require_roles
from app.services.ai_text import (
    build_call_script,
    build_client_quiz_summary_fast,
    build_manager_summary_fast,
    build_quiz_client_preview_summary,
    try_gigachat_client_summary_only,
    try_gigachat_manager_summary_only,
)
from app.services.telegram_notify import notify_manager_assigned_by_admin, notify_new_lead_broadcast
from app.services.transcription import transcribe_audio

router = APIRouter(prefix="/api/leads", tags=["leads"])
_log = logging.getLogger(__name__)


async def _notify_manager_assigned_async(manager_id: UUID, lead_id: UUID) -> None:
    """Фоновая отправка в Telegram менеджеру после назначения админом."""
    if not settings.TELEGRAM_BOT_TOKEN.strip():
        return
    async with async_session_maker() as db:
        mgr = await db.get(User, manager_id)
        if not mgr or not (mgr.telegram_user_id or "").strip():
            return
        lead = await db.get(Lead, lead_id)
        if not lead:
            return
        req = lead_request_number(lead)
        await notify_manager_assigned_by_admin(
            telegram_chat_id=mgr.telegram_user_id.strip(),
            lead_id=str(lead.id),
            request_number=req,
            client_name=lead.name,
            client_phone=lead.phone,
        )


async def _notify_telegram_new_pool_lead(
    lead_id: UUID,
    name: str,
    phone: str,
    summary: str,
    request_number: str,
) -> None:
    if not settings.TELEGRAM_BOT_TOKEN.strip():
        return
    await notify_new_lead_broadcast(
        lead_id=str(lead_id),
        name=name,
        phone=phone,
        summary=summary,
        request_number=request_number,
    )


async def _run_enrich_lead_summary(lead_id: UUID) -> None:
    """После быстрого сохранения — обновить ai_summary (менеджер) и ai_summary_client через GigaChat."""
    async with async_session_maker() as db:
        try:
            lead = await db.get(Lead, lead_id)
            if not lead:
                return
            answers = normalize_lead_answers(lead.answers or {})
            mgr = try_gigachat_manager_summary_only(answers)
            cli = try_gigachat_client_summary_only(answers)
            if mgr:
                lead.ai_summary = mgr
            if cli:
                lead.ai_summary_client = cli
            if mgr or cli:
                await db.commit()
        except Exception:
            _log.warning("Не удалось обновить ИИ-резюме для заявки %s", lead_id, exc_info=True)


def normalize_lead_answers(raw: dict[str, Any]) -> dict[str, Any]:
    """Приводит answers к виду с list steps (иногда клиент/БД отдаёт строку JSON)."""
    if not isinstance(raw, dict):
        return {"steps": []}
    cur: dict[str, Any] = raw
    for _ in range(8):
        if "steps" in cur:
            break
        nxt = cur.get("answers")
        if isinstance(nxt, dict):
            cur = nxt
        else:
            break
    out = dict(cur)
    steps = out.get("steps")
    if isinstance(steps, str):
        try:
            out["steps"] = json.loads(steps)
        except (json.JSONDecodeError, TypeError):
            out["steps"] = []
    if out.get("steps") is None:
        out["steps"] = []
    if not isinstance(out["steps"], list):
        out["steps"] = []
    return out


def lead_request_number(lead: Lead) -> str:
    return f"REQ-{str(lead.id).replace('-', '')[:8].upper()}"


def answers_room(answers: dict) -> str | None:
    if answers.get("room_type"):
        return answers.get("room_type")
    steps = answers.get("steps")
    if isinstance(steps, list) and steps:
        first = steps[0]
        if isinstance(first, dict):
            v = first.get("value")
            return str(v) if v is not None else None
    return None


async def _manager_active_leads_count(db: AsyncSession, manager_id: UUID) -> int:
    r = await db.execute(
        select(func.count())
        .select_from(Lead)
        .where(Lead.assigned_manager_id == manager_id, Lead.status == LeadStatus.in_progress)
    )
    return int(r.scalar_one())


def _manager_can_view_lead(user: User, lead: Lead) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role != UserRole.manager:
        return False
    if lead.status == LeadStatus.pending and lead.assigned_manager_id is None:
        return True
    return lead.assigned_manager_id == user.id


def _manager_can_mutate_lead(user: User, lead: Lead) -> bool:
    if user.role == UserRole.admin:
        return True
    if user.role != UserRole.manager:
        return False
    if lead.assigned_manager_id != user.id:
        return False
    if lead.status == LeadStatus.pending:
        return False
    return lead.status in (LeadStatus.in_progress, LeadStatus.completed)


def _can_patch_callback(user: User, lead: Lead) -> bool:
    if user.role == UserRole.admin:
        return True
    return _manager_can_mutate_lead(user, lead)


async def _lead_list_items(db: AsyncSession, leads: list[Lead]) -> list[LeadListItem]:
    ids = {l.assigned_manager_id for l in leads if l.assigned_manager_id}
    names: dict[UUID, str] = {}
    if ids:
        ur = await db.execute(select(User).where(User.id.in_(ids)))
        for u in ur.scalars().all():
            names[u.id] = u.full_name
    out: list[LeadListItem] = []
    for lead in leads:
        aid = lead.assigned_manager_id
        out.append(
            LeadListItem(
                id=lead.id,
                name=lead.name,
                phone=lead.phone,
                room_type=answers_room(lead.answers or {}),
                budget=answers_budget(lead.answers or {}),
                status=lead.status,
                created_at=lead.created_at,
                assigned_manager_id=aid,
                assigned_manager_name=names.get(aid) if aid else None,
                pool_entered_at=lead.pool_entered_at,
                callback_at=lead.callback_at,
                callback_note=lead.callback_note,
            )
        )
    return out


def answers_budget(answers: dict) -> str | None:
    if answers.get("budget"):
        return answers.get("budget")
    steps = answers.get("steps")
    if isinstance(steps, list):
        for raw in reversed(steps):
            if not isinstance(raw, dict):
                continue
            title = (raw.get("title") or "").lower()
            sid = str(raw.get("id") or "")
            if "бюджет" in title or sid == "step5":
                v = raw.get("value")
                return str(v) if v is not None else None
    return None


@router.post("/preview-summary", response_model=SummaryPreviewResponse)
async def preview_summary(body: SummaryPreviewBody):
    answers = normalize_lead_answers(body.answers)
    return SummaryPreviewResponse(summary=build_quiz_client_preview_summary(answers))


@router.post("/preview-call-script", response_model=CallScriptResponse)
async def preview_call_script(body: SummaryPreviewBody):
    answers = normalize_lead_answers(body.answers)
    return CallScriptResponse(script=build_call_script(answers))


@router.post("", response_model=LeadCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    body: LeadCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if not body.consent:
        raise HTTPException(status_code=400, detail="Нужно согласие на обработку данных")

    answers = normalize_lead_answers(body.answers)
    if body.session_id and isinstance(answers, dict):
        answers = {**answers, "_analytics_session": str(body.session_id)[:64]}
    qz_id = body.quiz_schema_id if body.quiz_schema_id and body.quiz_schema_id > 0 else None
    if qz_id is not None and isinstance(answers, dict):
        answers = {**answers, "_quiz_schema_id": qz_id}
    summary_mgr = build_manager_summary_fast(answers)
    summary_client = build_client_quiz_summary_fast(answers)
    script = build_call_script(answers)

    now = datetime.now(timezone.utc)
    lead = Lead(
        quiz_schema_id=qz_id,
        name=body.name.strip(),
        phone=body.phone.strip(),
        email=(body.email.strip() if body.email else None),
        comment=body.comment.strip() if body.comment else None,
        consent=body.consent,
        answers=answers,
        ai_summary=summary_mgr,
        ai_summary_client=summary_client,
        call_script=script,
        status=LeadStatus.pending,
        pool_entered_at=now,
        page_url=body.page_url,
        utm_source=body.utm_source,
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    background_tasks.add_task(_run_enrich_lead_summary, lead.id)

    req_num = lead_request_number(lead)
    background_tasks.add_task(
        _notify_telegram_new_pool_lead,
        lead.id,
        lead.name,
        lead.phone,
        summary_mgr,
        req_num,
    )

    return LeadCreateResponse(
        id=lead.id,
        request_number=req_num,
        ai_summary=summary_mgr,
        ai_summary_client=summary_client,
        page_url=lead.page_url,
        utm_source=lead.utm_source,
    )


@router.get("", response_model=list[LeadListItem])
async def list_leads(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager, UserRole.admin)),
    bucket: str | None = Query(
        None,
        description="Менеджер: pool | active | completed. Админ не указывает.",
    ),
    status_filter: LeadStatus | None = Query(None, alias="status"),
    assigned_manager_id: UUID | None = Query(None, description="Админ: фильтр по назначенному менеджеру"),
    only_pool: bool = Query(False, description="Админ: только общий пул (ожидают, без назначения)"),
):
    q = select(Lead)

    if user.role == UserRole.manager:
        b = (bucket or "").strip().lower()
        if b not in ("pool", "active", "completed"):
            raise HTTPException(
                status_code=400,
                detail="Укажите bucket=pool (общий пул), active (мои в работе) или completed (мои завершённые)",
            )
        if b == "pool":
            q = q.where(Lead.status == LeadStatus.pending, Lead.assigned_manager_id.is_(None))
        elif b == "active":
            q = q.where(Lead.assigned_manager_id == user.id, Lead.status == LeadStatus.in_progress)
        else:
            q = q.where(Lead.assigned_manager_id == user.id, Lead.status == LeadStatus.completed)
    else:
        if only_pool:
            q = q.where(Lead.status == LeadStatus.pending, Lead.assigned_manager_id.is_(None))
        if status_filter is not None:
            q = q.where(Lead.status == status_filter)
        if assigned_manager_id is not None:
            q = q.where(Lead.assigned_manager_id == assigned_manager_id)

    pool_order = False
    if user.role == UserRole.manager:
        b = (bucket or "").strip().lower()
        pool_order = b == "pool"
    elif only_pool or status_filter == LeadStatus.pending:
        pool_order = True

    if pool_order:
        wait_col = func.coalesce(Lead.pool_entered_at, Lead.created_at)
        q = q.order_by(wait_col.asc(), Lead.created_at.asc())
    else:
        q = q.order_by(Lead.created_at.desc())

    r = await db.execute(q)
    leads = list(r.scalars().all())
    return await _lead_list_items(db, leads)


@router.get(
    "/{lead_id}",
    response_model=Union[LeadPublicView, LeadManagerDetail],
    responses={200: {"description": "Публичный статус или полная карточка для менеджера/админа"}},
)
async def get_lead(
    lead_id: UUID,
    user: Annotated[User | None, Depends(get_optional_user)],
    db: AsyncSession = Depends(get_db),
):
    lr = await db.execute(
        select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.reminders))
    )
    lead = lr.scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    req_num = lead_request_number(lead)
    if user is not None and user.role in (UserRole.manager, UserRole.admin):
        if user.role == UserRole.manager and not _manager_can_view_lead(user, lead):
            raise HTTPException(status_code=403, detail="Заявка назначена другому менеджеру")
        nr = await db.execute(
            select(Note).where(Note.lead_id == lead.id).order_by(Note.created_at.asc())
        )
        notes = nr.scalars().all()
        rems = sorted(lead.reminders, key=lambda x: x.remind_at)
        mgr_ids = {r.manager_id for r in rems}
        mnames: dict[UUID, str] = {}
        if mgr_ids:
            ur = await db.execute(select(User).where(User.id.in_(mgr_ids)))
            for u in ur.scalars().all():
                mnames[u.id] = u.full_name
        reminder_rows = [
            ReminderOut(
                id=r.id,
                remind_at=r.remind_at,
                sent=r.sent,
                manager_id=r.manager_id,
                manager_name=mnames.get(r.manager_id),
            )
            for r in rems
        ]
        base = LeadDetail.model_validate(lead)
        return LeadManagerDetail(
            **base.model_dump(),
            notes=[NoteOut.model_validate(n) for n in notes],
            reminders=reminder_rows,
            request_number=req_num,
        )
    return LeadPublicView(
        id=lead.id,
        request_number=req_num,
        status=lead.status,
        answers=lead.answers or {},
        ai_summary_client=lead.ai_summary_client,
        updated_at=lead.updated_at,
    )


@router.patch("/{lead_id}/status", response_model=LeadDetail)
async def patch_lead_status(
    lead_id: UUID,
    body: LeadStatusPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager)),
):
    """Менеджер: только перевод своей заявки из «в работе» в «завершена»."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if body.status != LeadStatus.completed:
        raise HTTPException(status_code=400, detail="Доступно только status=completed")
    if lead.status != LeadStatus.in_progress or lead.assigned_manager_id != user.id:
        raise HTTPException(status_code=403, detail="Завершить можно только свою заявку в работе")

    lead.status = LeadStatus.completed
    lead.callback_at = None
    lead.callback_note = None
    lead.callback_due_notified = False
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.patch("/{lead_id}/admin", response_model=LeadDetail)
async def patch_lead_admin(
    lead_id: UUID,
    body: LeadAdminPatch,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    prev_assign = lead.assigned_manager_id
    was_in_pool = lead.status == LeadStatus.pending and lead.assigned_manager_id is None

    patch = body.model_dump(exclude_unset=True)
    new_status: LeadStatus = patch.get("status", lead.status)
    new_assign: UUID | None = (
        patch["assigned_manager_id"] if "assigned_manager_id" in patch else lead.assigned_manager_id
    )

    if (
        "assigned_manager_id" in patch
        and patch["assigned_manager_id"] is not None
        and "status" not in patch
        and lead.status == LeadStatus.pending
    ):
        new_status = LeadStatus.in_progress

    if new_status == LeadStatus.pending:
        new_assign = None
    elif new_status == LeadStatus.in_progress and new_assign is None:
        raise HTTPException(status_code=400, detail="Для статуса «в работе» назначьте менеджера")

    lead.status = new_status
    lead.assigned_manager_id = new_assign
    now_in_pool = lead.status == LeadStatus.pending and lead.assigned_manager_id is None
    if now_in_pool and not was_in_pool:
        lead.pool_entered_at = datetime.now(timezone.utc)
    elif not now_in_pool:
        lead.pool_entered_at = None

    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    if new_assign is not None and new_assign != prev_assign:
        background_tasks.add_task(_notify_manager_assigned_async, new_assign, lead.id)
    return LeadDetail.model_validate(lead)


@router.patch("/{lead_id}/callback", response_model=LeadDetail)
async def patch_lead_callback(
    lead_id: UUID,
    body: LeadCallbackPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager, UserRole.admin)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if not _can_patch_callback(user, lead):
        raise HTTPException(status_code=403, detail="Нет доступа к этой заявке")

    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="Укажите callback_at и/или callback_note")

    if "callback_at" in patch:
        lead.callback_at = patch["callback_at"]
        lead.callback_due_notified = False
    if "callback_note" in patch:
        note = patch["callback_note"]
        lead.callback_note = note.strip() if isinstance(note, str) and note.strip() else None
        lead.callback_due_notified = False

    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/claim", response_model=LeadDetail)
async def claim_lead(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if lead.status != LeadStatus.pending or lead.assigned_manager_id is not None:
        raise HTTPException(status_code=400, detail="Заявка не в общем пуле")
    cap = max(1, int(settings.MANAGER_MAX_ACTIVE_LEADS))
    if await _manager_active_leads_count(db, user.id) >= cap:
        raise HTTPException(
            status_code=409,
            detail=f"Лимит активных заявок ({cap}). Завершите или верните заявку в пул.",
        )
    lead.status = LeadStatus.in_progress
    lead.assigned_manager_id = user.id
    lead.pool_entered_at = None
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/release", response_model=LeadDetail)
async def release_lead_to_pool(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if lead.status != LeadStatus.in_progress or lead.assigned_manager_id != user.id:
        raise HTTPException(status_code=403, detail="Вернуть в пул можно только свою заявку в работе")
    lead.status = LeadStatus.pending
    lead.assigned_manager_id = None
    lead.pool_entered_at = datetime.now(timezone.utc)
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return LeadDetail.model_validate(lead)


@router.post("/{lead_id}/notes", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_note(
    lead_id: UUID,
    body: NoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager, UserRole.admin)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if user.role == UserRole.manager and not _manager_can_mutate_lead(user, lead):
        raise HTTPException(status_code=403, detail="Сначала возьмите заявку в работу")
    note = Note(lead_id=lead.id, author_id=user.id, body=body.text.strip(), is_voice=False)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return NoteOut.model_validate(note)


_MAX_VOICE_BYTES = 24 * 1024 * 1024  # лимит провайдеров ~25 МБ


@router.post("/{lead_id}/notes/voice", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def add_voice_note(
    lead_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager, UserRole.admin)),
    file: UploadFile = File(...),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if user.role == UserRole.manager and not _manager_can_mutate_lead(user, lead):
        raise HTTPException(status_code=403, detail="Сначала возьмите заявку в работу")
    raw = await file.read()
    if len(raw) > _MAX_VOICE_BYTES:
        raise HTTPException(status_code=413, detail="Файл слишком большой (макс. ~24 МБ)")

    fn = file.filename or "audio.webm"
    text = await transcribe_audio(raw, fn)
    if text:
        body = text
    else:
        has_key = bool((settings.GROQ_API_KEY or "").strip() or (settings.HUGGINGFACE_API_TOKEN or "").strip())
        if not has_key:
            body = (
                "[Голосовая заметка] Укажите в .env GROQ_API_KEY или HUGGINGFACE_API_TOKEN для транскрипции. "
                f"Файл: {fn}"
            )
        else:
            body = (
                f"[Голосовая заметка] Не удалось распознать речь. "
                f"Если в логах бэкенда Groq отвечает 403 Forbidden — проверьте GROQ_API_KEY в backend/.env, "
                f"регион/IP и права на модель в консоли Groq. Файл: {fn}"
            )

    note = Note(lead_id=lead.id, author_id=user.id, body=body, is_voice=True)
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return NoteOut.model_validate(note)


@router.post("/{lead_id}/reminders", status_code=status.HTTP_202_ACCEPTED)
async def create_reminder(
    lead_id: UUID,
    body: ReminderCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.manager, UserRole.admin)),
):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Заявка не найдена")
    if user.role == UserRole.manager and not _manager_can_mutate_lead(user, lead):
        raise HTTPException(status_code=403, detail="Сначала возьмите заявку в работу")
    target_manager_id = user.id
    if user.role == UserRole.admin and lead.assigned_manager_id is not None:
        target_manager_id = lead.assigned_manager_id
    r = Reminder(lead_id=lead.id, manager_id=target_manager_id, remind_at=body.remind_at, sent=False)
    db.add(r)
    await db.commit()
    return {"ok": True, "message": "Напоминание сохранено; отправка в Telegram — в следующей итерации"}
