"""Telegram-бот для менеджеров: вход по ссылке из кабинета на сайте, пул, уведомления.

Запуск из каталога backend:
  python bot_worker.py

Нужны TELEGRAM_BOT_TOKEN, поднятая БД (как у API). На API в .env задайте TELEGRAM_BOT_USERNAME (без @)
для кнопки «Войти в Telegram» на сайте. Опционально TELEGRAM_MANAGER_CHAT_ID — дублировать уведомления
о новых заявках в общий чат."""

from __future__ import annotations

import logging
import sys

from telegram.ext import Application, ContextTypes, JobQueue

from app.config import settings
from app.telegram_bot.handlers import register_handlers
from app.telegram_bot.jobs import run_all_scheduled_telegram_jobs

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _scheduled_job(_context: ContextTypes.DEFAULT_TYPE) -> None:
    await run_all_scheduled_telegram_jobs()


async def post_init(application: Application) -> None:
    jq = application.job_queue
    if jq:
        jq.run_repeating(_scheduled_job, interval=60.0, first=25.0, name="studio_telegram_jobs")
        logger.info("Напоминания (перезвон / reminders): каждые 60 с")
    else:
        logger.warning("JobQueue недоступен — установите python-telegram-bot[job-queue]")


def main() -> None:
    token = settings.TELEGRAM_BOT_TOKEN.strip()
    if not token:
        logger.error("Укажите TELEGRAM_BOT_TOKEN в .env")
        sys.exit(1)
    application = (
        Application.builder()
        .token(token)
        .job_queue(JobQueue())
        .post_init(post_init)
        .build()
    )
    register_handlers(application)
    logger.info("Бот запущен: /start — ссылка с сайта, пул и уведомления")
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
