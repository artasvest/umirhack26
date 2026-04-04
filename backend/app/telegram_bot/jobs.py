"""Фоновые напоминания для бота (polling + JobQueue)."""

from __future__ import annotations

import html
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session_maker
from app.models import Lead, LeadStatus, Reminder, User
from app.services.telegram_notify import send_message

logger = logging.getLogger(__name__)


def _req_num(lead_id) -> str:
    return f"REQ-{str(lead_id).replace('-', '')[:8].upper()}"


async def run_callback_due_reminders() -> None:
    """Напоминание «перезвонить» по полю callback_at (после наступления времени, один раз до смены callback в API)."""
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        r = await db.execute(
            select(Lead).where(
                Lead.callback_at.isnot(None),
                Lead.callback_at <= now,
                Lead.callback_due_notified.is_(False),
                Lead.status == LeadStatus.in_progress,
                Lead.assigned_manager_id.isnot(None),
            )
        )
        leads = r.scalars().all()
        for lead in leads:
            mgr = await db.get(User, lead.assigned_manager_id)
            if not mgr or not (mgr.telegram_user_id or "").strip():
                continue
            cid = mgr.telegram_user_id.strip()
            note = html.escape((lead.callback_note or "").strip()[:400])
            ca = lead.callback_at.strftime("%d.%m.%Y %H:%M UTC") if lead.callback_at else ""
            text = (
                f"🔔 <b>Перезвонить</b> {_req_num(lead.id)}\n"
                f"Клиент: {html.escape(lead.name)} · {html.escape(lead.phone)}\n"
                f"Время: {ca}\n"
                f"{note}"
            )
            try:
                ok = await send_message(cid, text)
            except Exception:
                logger.exception("send_message callback reminder")
                ok = False
            if ok:
                lead.callback_due_notified = True
        await db.commit()


async def run_db_reminders() -> None:
    """Напоминания из таблицы reminders (как с сайта)."""
    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        r = await db.execute(select(Reminder).where(Reminder.sent.is_(False), Reminder.remind_at <= now))
        rems = r.scalars().all()
        for rem in rems:
            mgr = await db.get(User, rem.manager_id)
            lead = await db.get(Lead, rem.lead_id)
            if not mgr or not (mgr.telegram_user_id or "").strip():
                rem.sent = True
                continue
            if not lead:
                rem.sent = True
                continue
            text = (
                f"⏰ <b>Напоминание</b> {_req_num(lead.id)}\n"
                f"{html.escape(lead.name)} · {html.escape(lead.phone)}"
            )
            try:
                ok = await send_message(mgr.telegram_user_id.strip(), text)
            except Exception:
                logger.exception("send_message db reminder")
                ok = False
            if ok:
                rem.sent = True
        await db.commit()


async def run_all_scheduled_telegram_jobs() -> None:
    await run_callback_due_reminders()
    await run_db_reminders()
