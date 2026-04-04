import csv
from datetime import datetime, timezone
from io import StringIO

from fastapi import APIRouter, Depends, Response
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AnalyticsEvent, AnalyticsSession, Lead, User, UserRole
from app.schemas import AnalyticsTrackBody
from app.security import require_roles

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


async def _touch_analytics_session(
    db: AsyncSession,
    session_id: str,
    step_key: str | None,
    quiz_schema_id: int | None,
) -> None:
    if not step_key:
        return
    sk = step_key[:64]
    now = datetime.now(timezone.utc)
    r = await db.execute(select(AnalyticsSession).where(AnalyticsSession.session_id == session_id))
    row = r.scalar_one_or_none()
    if row:
        row.last_activity_at = now
        row.last_step_key = sk
        row.quiz_schema_id = quiz_schema_id
    else:
        db.add(
            AnalyticsSession(
                session_id=session_id,
                last_activity_at=now,
                last_step_key=sk,
                quiz_schema_id=quiz_schema_id,
            )
        )


@router.delete("/events")
async def clear_analytics_events(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """Удалить все события воронки (step_view / step_drop / step_answer и т.д.). Заявки не трогаем."""
    sr = await db.execute(delete(AnalyticsSession))
    n_sess = sr.rowcount if sr.rowcount is not None else 0
    er = await db.execute(delete(AnalyticsEvent))
    n = er.rowcount if er.rowcount is not None else 0
    await db.commit()
    return {"deleted": n, "deleted_sessions": n_sess}


@router.post("/track")
async def track_event(body: AnalyticsTrackBody, db: AsyncSession = Depends(get_db)):
    sid = body.session_id[:64]
    et = body.event_type[:64]
    sk = body.step_key[:64] if body.step_key else None
    qz = body.quiz_schema_id if body.quiz_schema_id and body.quiz_schema_id > 0 else None
    ev = AnalyticsEvent(
        quiz_schema_id=qz,
        session_id=sid,
        event_type=et,
        step_key=sk,
        payload=body.payload,
    )
    db.add(ev)
    if et in ("step_view", "step_answer") and sk:
        await _touch_analytics_session(db, sid, sk, qz)
    await db.commit()
    return {"ok": True}


@router.get("")
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    vr = await db.execute(
        select(AnalyticsEvent.step_key, func.count())
        .where(
            AnalyticsEvent.event_type == "step_view",
            AnalyticsEvent.step_key.isnot(None),
        )
        .group_by(AnalyticsEvent.step_key)
    )
    views = vr.all()
    dr = await db.execute(
        select(AnalyticsEvent.step_key, func.count())
        .where(
            AnalyticsEvent.event_type == "step_drop",
            AnalyticsEvent.step_key.isnot(None),
        )
        .group_by(AnalyticsEvent.step_key)
    )
    drops = dr.all()
    view_map = {k: v for k, v in views if k}
    drop_map = {k: v for k, v in drops if k}
    keys = sorted(set(view_map) | set(drop_map))
    funnel = [
        {
            "step_key": k,
            "views": view_map.get(k, 0),
            "drops": drop_map.get(k, 0),
        }
        for k in keys
    ]

    day_r = await db.execute(
        select(func.date(Lead.created_at).label("d"), func.count())
        .group_by(func.date(Lead.created_at))
        .order_by(func.date(Lead.created_at))
    )
    day_counts = day_r.all()
    leads_by_day = [{"date": str(d), "count": c} for d, c in day_counts if d]

    return {"funnel": funnel, "leads_by_day": leads_by_day}


@router.get("/export/csv")
async def export_leads_csv(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    r = await db.execute(select(Lead).order_by(Lead.created_at.desc()))
    leads = r.scalars().all()
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "created_at",
            "status",
            "name",
            "phone",
            "email",
            "room_type",
            "budget",
            "area_sqm",
            "style",
            "zones",
        ]
    )
    for lead in leads:
        a = lead.answers or {}
        zones = a.get("zones") or []
        w.writerow(
            [
                str(lead.id),
                lead.created_at.isoformat() if lead.created_at else "",
                lead.status.value,
                lead.name,
                lead.phone,
                lead.email or "",
                a.get("room_type", ""),
                a.get("budget", ""),
                a.get("area_sqm", ""),
                a.get("style", ""),
                ";".join(zones) if isinstance(zones, list) else str(zones),
            ]
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leads.csv"'},
    )
