"""Обработчики: вход по ссылке с сайта, пул, мои заявки, карточка, claim/done."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import settings
from app.database import async_session_maker
from app.models import Lead, LeadStatus, User, UserRole
from app.services.telegram_link import consume_telegram_link_token

MAIN_KB = ReplyKeyboardMarkup(
    [["Пул заявок", "Мои в работе"], ["Помощь", "Выйти"]],
    resize_keyboard=True,
)


def _req_num(lead: Lead) -> str:
    return f"REQ-{str(lead.id).replace('-', '')[:8].upper()}"


async def _get_user_by_tg(db, tg_id: str) -> User | None:
    r = await db.execute(select(User).where(User.telegram_user_id == tg_id))
    return r.scalar_one_or_none()


def _status_ru(s: LeadStatus) -> str:
    return {"pending": "в пуле", "in_progress": "в работе", "completed": "завершена"}.get(s.value, s.value)


def _lead_card_html(lead: Lead) -> str:
    summ = (lead.ai_summary or lead.ai_summary_client or "")[:1200]
    cb = ""
    if lead.callback_at:
        cb = lead.callback_at.strftime("%d.%m.%Y %H:%M UTC")
    note = html.escape((lead.callback_note or "").strip()[:500])
    lines = [
        f"<b>{html.escape(_req_num(lead))}</b> · {_status_ru(lead.status)}",
        f"Имя: {html.escape(lead.name)}",
        f"Телефон: {html.escape(lead.phone)}",
    ]
    if lead.email:
        lines.append(f"Email: {html.escape(lead.email)}")
    if cb:
        lines.append(f"Перезвонить: {html.escape(cb)}")
    if note:
        lines.append(f"Заметка: {note}")
    if summ:
        lines.append("")
        lines.append(f"<i>{html.escape(summ)}</i>")
    return "\n".join(lines)


def _keyboard_for_lead(lead: Lead, viewer_id: UUID, viewer_role: UserRole) -> InlineKeyboardMarkup | None:
    rows: list[list[InlineKeyboardButton]] = []
    lid = str(lead.id)
    if (
        lead.status == LeadStatus.pending
        and lead.assigned_manager_id is None
        and viewer_role == UserRole.manager
    ):
        rows.append([InlineKeyboardButton("Взять в работу", callback_data=f"claim:{lid}")])
    if lead.status == LeadStatus.in_progress and lead.assigned_manager_id == viewer_id:
        rows.append([InlineKeyboardButton("Завершить", callback_data=f"done:{lid}")])
    if not rows:
        return None
    return InlineKeyboardMarkup(rows)


async def _manager_active_count(db, manager_id: UUID) -> int:
    r = await db.execute(
        select(func.count())
        .select_from(Lead)
        .where(Lead.assigned_manager_id == manager_id, Lead.status == LeadStatus.in_progress)
    )
    return int(r.scalar_one())


async def cmd_start_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg = str(update.effective_user.id)
    args = context.args or []

    async with async_session_maker() as db:
        u = await _get_user_by_tg(db, tg)
        if u:
            await update.message.reply_html(
                f"Вы вошли как <b>{html.escape(u.email)}</b>\n{html.escape(u.full_name)}",
                reply_markup=MAIN_KB,
            )
            await update.message.reply_html(
                "Кнопки: <b>Пул заявок</b> — общий пул (как на сайте), "
                "<b>Мои в работе</b> — ваши активные. "
                "О новых заявках в пуле придёт сообщение с кнопкой «Взять».\n"
                "Напоминание «перезвонить» — когда наступит время, указанное в карточке.",
            )
            return

        if not args:
            await update.message.reply_html(
                "Чтобы подключить бота, откройте <b>ссылку из кабинета</b> на сайте "
                "(кнопка «Войти в Telegram»). Ссылка одноразовая и действует несколько минут. "
                "Если не открывается — сгенерируйте новую на сайте."
            )
            return

        token = args[0].strip()
        ok = await consume_telegram_link_token(db, token, tg)
        if not ok:
            await update.message.reply_text(
                "Ссылка недействительна или устарела. Зайдите на сайт в кабинет и сгенерируйте новую."
            )
            return
        u = await _get_user_by_tg(db, tg)

    fn = (u.full_name if u else "") or ""
    await update.message.reply_text(
        f"Telegram привязан к аккаунту. Здравствуйте, {fn}!",
        reply_markup=MAIN_KB,
    )


async def cmd_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg = str(update.effective_user.id)
    async with async_session_maker() as db:
        u = await _get_user_by_tg(db, tg)
        if u:
            u.telegram_user_id = None
            await db.commit()
    await update.message.reply_text(
        "Вы вышли из аккаунта в боте. На сайте сессия не сбрасывается.",
        reply_markup=ReplyKeyboardRemove(),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    await update.message.reply_html(
        "<b>Помощь</b>\n"
        "/start — меню или вход по ссылке с сайта\n"
        "/pool — пул заявок\n"
        "/my — мои в работе\n"
        "/logout — отвязать Telegram от аккаунта\n\n"
        "Уведомления: новая заявка в пуле, напоминание о перезвоне (по времени в карточке).",
    )


async def show_pool(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg = str(update.effective_user.id)
    async with async_session_maker() as db:
        u = await _get_user_by_tg(db, tg)
        if not u:
            await update.message.reply_text("Сначала подключите бота по ссылке из кабинета на сайте (/start).")
            return
        vid, vrole = u.id, u.role
        q = (
            select(Lead)
            .where(Lead.status == LeadStatus.pending, Lead.assigned_manager_id.is_(None))
            .order_by(func.coalesce(Lead.pool_entered_at, Lead.created_at).asc())
            .limit(15)
        )
        r = await db.execute(q)
        leads = list(r.scalars().all())
    if not leads:
        await update.message.reply_text("Пул пуст.")
        return
    await update.message.reply_text(f"Пул заявок (показано до 15). В списке: {len(leads)}.")
    for lead in leads:
        kb = _keyboard_for_lead(lead, vid, vrole)
        await update.message.reply_html(_lead_card_html(lead), reply_markup=kb)


async def show_my(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    tg = str(update.effective_user.id)
    async with async_session_maker() as db:
        u = await _get_user_by_tg(db, tg)
        if not u:
            await update.message.reply_text("Сначала подключите бота по ссылке из кабинета на сайте (/start).")
            return
        vid, vrole = u.id, u.role
        q = (
            select(Lead)
            .where(Lead.assigned_manager_id == u.id, Lead.status == LeadStatus.in_progress)
            .order_by(Lead.updated_at.desc())
            .limit(20)
        )
        r = await db.execute(q)
        leads = list(r.scalars().all())
    if not leads:
        await update.message.reply_text("Нет заявок в работе у вас.")
        return
    for lead in leads:
        kb = _keyboard_for_lead(lead, vid, vrole)
        await update.message.reply_html(_lead_card_html(lead), reply_markup=kb)


async def on_text_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    t = update.message.text.strip()
    if t == "Пул заявок":
        await show_pool(update, context)
    elif t == "Мои в работе":
        await show_my(update, context)
    elif t == "Помощь":
        await cmd_help(update, context)
    elif t == "Выйти":
        await cmd_logout(update, context)


async def on_lead_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cq = update.callback_query
    if not cq or not cq.data:
        return
    if not cq.message:
        await cq.answer()
        return
    if cq.message.chat.type != "private":
        await cq.answer()
        return
    raw = cq.data
    if ":" not in raw:
        await cq.answer()
        return
    action, lid_s = raw.split(":", 1)
    if action == "take":
        action = "claim"
    try:
        lid = UUID(lid_s)
    except ValueError:
        await cq.answer("Некорректные данные", show_alert=True)
        return

    tg = str(cq.from_user.id)
    async with async_session_maker() as db:
        user = await _get_user_by_tg(db, tg)
        if not user:
            await cq.answer("Сначала подключите бота по ссылке с сайта: /start", show_alert=True)
            return
        lead = await db.get(Lead, lid)
        if not lead:
            await cq.answer("Заявка не найдена", show_alert=True)
            return

        if action == "view":
            await cq.answer()
            kb = _keyboard_for_lead(lead, user.id, user.role)
            await cq.message.reply_html(_lead_card_html(lead), reply_markup=kb)
            return

        if action == "claim":
            if user.role != UserRole.manager:
                await cq.answer("Из пула может взять только менеджер", show_alert=True)
                return
            if lead.status != LeadStatus.pending or lead.assigned_manager_id is not None:
                await cq.answer("Заявка уже не в пуле", show_alert=True)
                return
            cap = max(1, int(settings.MANAGER_MAX_ACTIVE_LEADS))
            if await _manager_active_count(db, user.id) >= cap:
                await cq.answer(f"Лимит активных заявок ({cap})", show_alert=True)
                return
            lead.status = LeadStatus.in_progress
            lead.assigned_manager_id = user.id
            lead.pool_entered_at = None
            lead.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await cq.answer("Взяли в работу")
            try:
                await cq.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        if action == "done":
            if lead.status != LeadStatus.in_progress or lead.assigned_manager_id != user.id:
                await cq.answer("Можно завершить только свою заявку в работе", show_alert=True)
                return
            lead.status = LeadStatus.completed
            lead.callback_at = None
            lead.callback_note = None
            lead.callback_due_notified = False
            lead.updated_at = datetime.now(timezone.utc)
            await db.commit()
            await cq.answer("Завершено")
            try:
                await cq.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return


def register_handlers(application: Application) -> None:
    _priv = filters.ChatType.PRIVATE
    application.add_handler(CommandHandler("start", cmd_start_entry, filters=_priv))
    application.add_handler(CommandHandler("logout", cmd_logout, filters=_priv))
    application.add_handler(CommandHandler("help", cmd_help, filters=_priv))
    application.add_handler(CommandHandler("pool", show_pool, filters=_priv))
    application.add_handler(CommandHandler("my", show_my, filters=_priv))
    application.add_handler(CallbackQueryHandler(on_lead_callback, pattern=r"^(view|claim|done|take):"))
    application.add_handler(
        MessageHandler(_priv & filters.TEXT & ~filters.COMMAND, on_text_buttons),
    )
