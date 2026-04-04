"""Расширенная аналитика: GET /api/admin/analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.default_quiz_schema import DEFAULT_QUIZ_SCHEMA
from app.models import AnalyticsEvent, AnalyticsSession, Lead, Note, QuizSchemaRow, Reminder, User, UserRole
from app.security import require_roles

router = APIRouter(prefix="/api/admin", tags=["admin-analytics"])


@router.delete("/analytics/data")
async def wipe_analytics_dashboard_data(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """События воронки, сессии активности, все заявки, напоминания и заметки. Пользователи и схема квиза не трогаются."""
    n_notes = (await db.execute(delete(Note))).rowcount or 0
    n_rem = (await db.execute(delete(Reminder))).rowcount or 0
    n_leads = (await db.execute(delete(Lead))).rowcount or 0
    n_events = (await db.execute(delete(AnalyticsEvent))).rowcount or 0
    n_sess = (await db.execute(delete(AnalyticsSession))).rowcount or 0
    await db.commit()
    return {
        "deleted_notes": n_notes,
        "deleted_reminders": n_rem,
        "deleted_leads": n_leads,
        "deleted_events": n_events,
        "deleted_sessions": n_sess,
    }


async def _submitted_session_ids(db: AsyncSession, quiz_filter: int | None) -> set[str]:
    out: set[str] = set()
    q = select(Lead)
    if quiz_filter is not None:
        q = q.where(Lead.quiz_schema_id == quiz_filter)
    r = await db.execute(q)
    for lead in r.scalars().all():
        a = lead.answers or {}
        if not isinstance(a, dict):
            continue
        sid = a.get("_analytics_session")
        if isinstance(sid, str) and sid.strip():
            out.add(sid.strip()[:64])
    return out


async def _idle_drop_counts_by_step(
    db: AsyncSession, idle_minutes: int, quiz_filter: int | None
) -> dict[str, int]:
    """Сессии без заявки, без активности дольше idle_minutes — по 1 дропу на last_step_key."""
    submitted = await _submitted_session_ids(db, quiz_filter)
    threshold = datetime.now(timezone.utc) - timedelta(minutes=idle_minutes)
    q = select(AnalyticsSession).where(
        AnalyticsSession.last_activity_at < threshold,
        AnalyticsSession.last_step_key.isnot(None),
    )
    if quiz_filter is not None:
        q = q.where(AnalyticsSession.quiz_schema_id == quiz_filter)
    r = await db.execute(q)
    rows = r.scalars().all()
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.session_id in submitted:
            continue
        counts[str(row.last_step_key)] += 1
    return dict(counts)


async def _avg_seconds_per_step_from_step_views(
    db: AsyncSession, segment_cap_seconds: float, quiz_filter: int | None
) -> dict[str, float]:
    cap = max(60.0, float(segment_cap_seconds))
    ev_q = select(
        AnalyticsEvent.session_id,
        AnalyticsEvent.step_key,
        AnalyticsEvent.created_at,
        AnalyticsEvent.id,
    ).where(
        AnalyticsEvent.event_type == "step_view",
        AnalyticsEvent.step_key.isnot(None),
    )
    if quiz_filter is not None:
        ev_q = ev_q.where(AnalyticsEvent.quiz_schema_id == quiz_filter)
    ev_q = ev_q.order_by(AnalyticsEvent.session_id, AnalyticsEvent.created_at, AnalyticsEvent.id)
    er = await db.execute(ev_q)
    evs = er.all()
    by_sid: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
    for sid, sk, ca, _eid in evs:
        if ca is None or not sk:
            continue
        by_sid[str(sid)].append((ca, str(sk)))

    sums: dict[str, float] = defaultdict(float)
    seg_n: dict[str, int] = defaultdict(int)
    for _sid, seq in by_sid.items():
        if len(seq) < 2:
            continue
        for i in range(len(seq) - 1):
            t0, k0 = seq[i]
            t1, _k1 = seq[i + 1]
            dt = (t1 - t0).total_seconds()
            if dt < 0:
                continue
            sums[k0] += min(dt, cap)
            seg_n[k0] += 1

    return {k: round(sums[k] / seg_n[k], 1) for k in sums if seg_n[k] > 0}


async def _active_schema(db: AsyncSession) -> dict[str, Any]:
    r = await db.execute(
        select(QuizSchemaRow)
        .where(QuizSchemaRow.is_active.is_(True))
        .order_by(QuizSchemaRow.id.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    if row and isinstance(row.schema, dict):
        return row.schema
    return DEFAULT_QUIZ_SCHEMA


def _node_title_map(schema: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in schema.get("nodes") or []:
        if isinstance(n, dict) and n.get("id"):
            tid = str(n["id"])
            out[tid] = str(n.get("title") or tid).strip() or tid
    return out


def _form_node_ids(schema: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for n in schema.get("nodes") or []:
        if isinstance(n, dict) and n.get("type") == "form" and n.get("id"):
            ids.add(str(n["id"]))
    return ids


async def _resolve_analytics_quiz_filter(db: AsyncSession, quiz_schema_id: int | None) -> int | None:
    if quiz_schema_id == 0:
        return None
    if quiz_schema_id is not None and quiz_schema_id > 0:
        return quiz_schema_id
    r = await db.execute(
        select(QuizSchemaRow)
        .where(QuizSchemaRow.is_active.is_(True))
        .order_by(QuizSchemaRow.id.desc())
        .limit(1)
    )
    row = r.scalar_one_or_none()
    return row.id if row else None


async def _schema_dict_for_analytics(db: AsyncSession, quiz_filter: int | None) -> dict[str, Any]:
    if quiz_filter is not None:
        r = await db.execute(select(QuizSchemaRow).where(QuizSchemaRow.id == quiz_filter))
        row = r.scalar_one_or_none()
        if row and isinstance(row.schema, dict):
            return row.schema
    return await _active_schema(db)


@router.get("/analytics/by-quiz")
async def analytics_summary_by_quiz(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
):
    """Сводка по каждому квизу в хранилище — для сравнения конверсии."""
    rr = await db.execute(select(QuizSchemaRow).order_by(QuizSchemaRow.id.desc()))
    rows = rr.scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        qf = r.id
        sch = r.schema if isinstance(r.schema, dict) else {}
        form_ids = _form_node_ids(sch)
        sr = await db.execute(
            select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
                AnalyticsEvent.event_type == "step_view",
                AnalyticsEvent.quiz_schema_id == qf,
            )
        )
        started = int(sr.scalar_one() or 0)
        if form_ids:
            cr = await db.execute(
                select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
                    AnalyticsEvent.event_type == "step_view",
                    AnalyticsEvent.quiz_schema_id == qf,
                    AnalyticsEvent.step_key.in_(form_ids),
                )
            )
            completed = int(cr.scalar_one() or 0)
        else:
            completed = 0
        subr = await db.execute(select(func.count(Lead.id)).where(Lead.quiz_schema_id == qf))
        submitted = int(subr.scalar_one() or 0)
        cr_pct = round(min(100.0, 100.0 * submitted / started), 1) if started else 0.0
        out.append(
            {
                "quiz_schema_id": r.id,
                "name": r.name,
                "is_active": r.is_active,
                "total_started": started,
                "total_completed": completed,
                "total_submitted": submitted,
                "completion_rate": cr_pct,
            }
        )
    return out


@router.get("/analytics")
async def admin_analytics_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
    quiz_schema_id: int | None = Query(
        None,
        description="Фильтр: id квиза, 0 = весь трафик, не указано = активный квиз",
    ),
):
    qf = await _resolve_analytics_quiz_filter(db, quiz_schema_id)
    schema = await _schema_dict_for_analytics(db, qf)
    title_by_id = _node_title_map(schema)
    form_ids = _form_node_ids(schema)

    ev_started = select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
        AnalyticsEvent.event_type == "step_view"
    )
    if qf is not None:
        ev_started = ev_started.where(AnalyticsEvent.quiz_schema_id == qf)
    tr = await db.execute(ev_started)
    total_started = int(tr.scalar_one() or 0)

    if form_ids:
        ev_done = select(func.count(func.distinct(AnalyticsEvent.session_id))).where(
            AnalyticsEvent.event_type == "step_view",
            AnalyticsEvent.step_key.in_(form_ids),
        )
        if qf is not None:
            ev_done = ev_done.where(AnalyticsEvent.quiz_schema_id == qf)
        dr = await db.execute(ev_done)
        total_completed = int(dr.scalar_one() or 0)
    else:
        total_completed = 0

    lq = select(func.count(Lead.id))
    if qf is not None:
        lq = lq.where(Lead.quiz_schema_id == qf)
    lr = await db.execute(lq)
    total_submitted = int(lr.scalar_one() or 0)

    if total_started:
        raw_pct = 100.0 * total_submitted / total_started
        completion_rate = round(min(100.0, raw_pct), 1)
    else:
        completion_rate = 0.0

    bounds_q = (
        select(
            AnalyticsEvent.session_id,
            func.min(AnalyticsEvent.created_at),
            func.max(AnalyticsEvent.created_at),
        )
        .where(AnalyticsEvent.event_type == "step_view")
        .group_by(AnalyticsEvent.session_id)
    )
    if qf is not None:
        bounds_q = select(
            AnalyticsEvent.session_id,
            func.min(AnalyticsEvent.created_at),
            func.max(AnalyticsEvent.created_at),
        ).where(
            AnalyticsEvent.event_type == "step_view",
            AnalyticsEvent.quiz_schema_id == qf,
        ).group_by(AnalyticsEvent.session_id)

    br = await db.execute(bounds_q)
    bounds = br.all()
    spans: list[float] = []
    for _sid, mn, mx in bounds:
        if mn and mx and mx > mn:
            spans.append((mx - mn).total_seconds())
    avg_time_seconds = round(sum(spans) / len(spans), 1) if spans else 0.0

    views_q = (
        select(AnalyticsEvent.step_key, func.count())
        .where(
            AnalyticsEvent.event_type == "step_view",
            AnalyticsEvent.step_key.isnot(None),
        )
        .group_by(AnalyticsEvent.step_key)
    )
    if qf is not None:
        views_q = (
            select(AnalyticsEvent.step_key, func.count())
            .where(
                AnalyticsEvent.event_type == "step_view",
                AnalyticsEvent.step_key.isnot(None),
                AnalyticsEvent.quiz_schema_id == qf,
            )
            .group_by(AnalyticsEvent.step_key)
        )
    vr = await db.execute(views_q)
    views = vr.all()
    idle_minutes = max(1, int(settings.ANALYTICS_DROP_IDLE_MINUTES))
    drop_map = {
        str(k): int(v) for k, v in (await _idle_drop_counts_by_step(db, idle_minutes, qf)).items()
    }
    avg_step_secs = await _avg_seconds_per_step_from_step_views(db, idle_minutes * 60.0, qf)
    view_map = {str(k): int(v) for k, v in views if k}

    keys_seen = set(view_map) | set(drop_map)
    ordered: list[str] = []
    for n in schema.get("nodes") or []:
        if isinstance(n, dict) and n.get("id"):
            nid = str(n["id"])
            if nid in keys_seen:
                ordered.append(nid)
    for k in sorted(keys_seen):
        if k not in ordered:
            ordered.append(k)

    funnel: list[dict[str, Any]] = []
    top_drop_row: dict[str, str] | None = None
    top_drops = -1

    for nid in ordered:
        v = view_map.get(nid, 0)
        d = drop_map.get(nid, 0)
        dr_pct = round(100.0 * d / v, 1) if v else 0.0
        funnel.append(
            {
                "node_id": nid,
                "title": title_by_id.get(nid, nid),
                "views": v,
                "drops": d,
                "drop_rate": dr_pct,
                "avg_seconds_on_step": avg_step_secs.get(nid),
            }
        )
        if d > top_drops:
            top_drops = d
            top_drop_row = {"node_id": nid, "title": title_by_id.get(nid, nid)}

    top_drop_step = top_drop_row if top_drop_row and top_drops > 0 else None

    dist_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def _ingest_answer_row(nid: str, payload: dict | None) -> None:
        if not nid:
            return
        p = payload or {}
        bt = str(p.get("block_type") or "").lower()
        if bt in ("form", "ai_summary"):
            return
        vals = p.get("values")
        if isinstance(vals, list):
            for item in vals:
                if item is not None and str(item).strip():
                    dist_map[nid][str(item).strip()] += 1
            return
        val = p.get("value")
        if val is not None and str(val).strip():
            dist_map[nid][str(val).strip()] += 1

    session_answered_nodes: set[tuple[str, str]] = set()
    latest_answer_payload: dict[tuple[str, str], dict | None] = {}
    ev_q = select(AnalyticsEvent).where(
        AnalyticsEvent.event_type == "step_answer",
        AnalyticsEvent.step_key.isnot(None),
    )
    if qf is not None:
        ev_q = ev_q.where(AnalyticsEvent.quiz_schema_id == qf)
    ev_q = ev_q.order_by(AnalyticsEvent.created_at.asc(), AnalyticsEvent.id.asc())
    ear = await db.execute(ev_q)
    for ev in ear.scalars().all():
        key = (str(ev.session_id), str(ev.step_key))
        session_answered_nodes.add(key)
        pl = ev.payload if isinstance(ev.payload, dict) else None
        latest_answer_payload[key] = pl
    for (_sid, nid), pl in latest_answer_payload.items():
        _ingest_answer_row(nid, pl)

    titles_from_leads: dict[str, str] = {}
    leads_q = select(Lead)
    if qf is not None:
        leads_q = leads_q.where(Lead.quiz_schema_id == qf)
    ldr = await db.execute(leads_q)
    for lead in ldr.scalars().all():
        a = lead.answers or {}
        lead_session: str | None = None
        if isinstance(a, dict):
            sid = a.get("_analytics_session")
            if isinstance(sid, str) and sid.strip():
                lead_session = sid.strip()[:64]
        steps = a.get("steps")
        if not isinstance(steps, list):
            continue
        for raw in steps:
            if not isinstance(raw, dict):
                continue
            nid = str(raw.get("id") or "")
            if not nid:
                continue
            bt = str(raw.get("blockType") or raw.get("block_type") or "").lower()
            if bt in ("form", "ai_summary"):
                continue
            if lead_session and (lead_session, nid) in session_answered_nodes:
                continue
            tit = str(raw.get("title") or "").strip()
            if tit:
                titles_from_leads[nid] = tit
            val = raw.get("value")
            if isinstance(val, list):
                for item in val:
                    if item is not None and str(item).strip():
                        dist_map[nid][str(item).strip()] += 1
            elif val is not None and str(val).strip():
                dist_map[nid][str(val).strip()] += 1

    answer_distribution: list[dict[str, Any]] = []
    for n in schema.get("nodes") or []:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        nid = str(n["id"])
        if nid not in dist_map:
            continue
        counts = dist_map[nid]
        total = sum(counts.values())
        opts = []
        for label, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            pct = round(100.0 * cnt / total, 1) if total else 0.0
            opts.append({"label": label, "count": cnt, "percent": pct})
        answer_distribution.append(
            {
                "node_id": nid,
                "title": titles_from_leads.get(nid) or title_by_id.get(nid, nid),
                "options": opts,
            }
        )

    ar = await db.execute(
        select(QuizSchemaRow)
        .where(QuizSchemaRow.is_active.is_(True))
        .order_by(QuizSchemaRow.id.desc())
        .limit(1)
    )
    active_row = ar.scalar_one_or_none()

    return {
        "total_started": total_started,
        "total_completed": total_completed,
        "total_submitted": total_submitted,
        "completion_rate": completion_rate,
        "avg_time_seconds": avg_time_seconds,
        "funnel": funnel,
        "top_drop_step": top_drop_step,
        "answer_distribution": answer_distribution,
        "drop_idle_minutes": idle_minutes,
        "quiz_filter_applied": qf,
        "active_quiz_schema_id": active_row.id if active_row else None,
    }
