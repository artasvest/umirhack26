import html

import httpx
from sqlalchemy import select

from app.config import settings
from app.database import async_session_maker
from app.models import User, UserRole


async def send_message(chat_id: str, text: str, reply_markup: dict | None = None) -> bool:
    token = settings.TELEGRAM_BOT_TOKEN.strip()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        body["reply_markup"] = reply_markup
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json=body)
        return r.status_code == 200


def inline_new_lead_keyboard(lead_id: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "Взять в работу", "callback_data": f"claim:{lead_id}"}],
        ]
    }


async def notify_new_lead_to_chat(
    chat_id: str,
    *,
    lead_id: str,
    name: str,
    phone: str,
    summary: str,
    request_number: str,
) -> bool:
    text = (
        "<b>Новая заявка в пуле</b>\n"
        f"№ {html.escape(request_number)}\n"
        f"Имя: {html.escape(name)}\n"
        f"Телефон: {html.escape(phone)}\n\n"
        f"<i>{html.escape(summary[:900])}</i>"
    )
    return await send_message(chat_id, text, reply_markup=inline_new_lead_keyboard(lead_id))


async def notify_new_lead_broadcast(
    *,
    lead_id: str,
    name: str,
    phone: str,
    summary: str,
    request_number: str,
) -> None:
    """Личные уведомления всем менеджерам с привязанным Telegram + опционально общий чат TELEGRAM_MANAGER_CHAT_ID."""
    chat_ids: list[str] = []
    async with async_session_maker() as db:
        r = await db.execute(
            select(User).where(
                User.role.in_((UserRole.manager, UserRole.admin)),
                User.telegram_user_id.isnot(None),
            )
        )
        for u in r.scalars().all():
            tid = (u.telegram_user_id or "").strip()
            if tid:
                chat_ids.append(tid)
    group = settings.TELEGRAM_MANAGER_CHAT_ID.strip()
    if group:
        chat_ids.append(group)
    seen: set[str] = set()
    for cid in chat_ids:
        if cid in seen:
            continue
        seen.add(cid)
        await notify_new_lead_to_chat(
            cid,
            lead_id=lead_id,
            name=name,
            phone=phone,
            summary=summary,
            request_number=request_number,
        )


async def notify_new_lead(
    chat_id: str,
    *,
    lead_id: str,
    name: str,
    phone: str,
    summary: str,
    request_number: str,
) -> bool:
    """Одна цель (чат); для рассылки менеджерам используйте notify_new_lead_broadcast."""
    return await notify_new_lead_to_chat(
        chat_id,
        lead_id=lead_id,
        name=name,
        phone=phone,
        summary=summary,
        request_number=request_number,
    )
