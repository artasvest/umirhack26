# Смарт-квиз для дизайн-студии

Монорепозиторий: **Vue 3 + TypeScript + Tailwind** (фронт), **FastAPI + PostgreSQL** (API), отдельный процесс **Telegram-бота** (polling + inline-кнопки).

## Быстрый старт

### 1. База данных

```bash
docker compose up -d
```

Параметры по умолчанию совпадают с `backend/.env.example` (пользователь `quiz`, БД `quizstudio`).

### 2. Backend

Рекомендуется **Python 3.11 или 3.12** (для 3.14 часть колёс на PyPI может быть недоступна).

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
copy .env.example .env   # при необходимости поправьте секреты и Telegram
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

При первом запуске создаются таблицы, админ из переменных `ADMIN_EMAIL` / `ADMIN_PASSWORD` (по умолчанию `admin@studio.local` / `admin123`) и запись схемы квиза по умолчанию.

`DATABASE_URL` должен использовать драйвер **psycopg v3**, например:

`postgresql+psycopg://quiz:quiz@localhost:5432/quizstudio`

### 3. Telegram

- В `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_MANAGER_CHAT_ID` (id чата, куда слать новые заявки).
- В отдельном терминале из каталога `backend`:

```bash
python bot_worker.py
```

Бот обрабатывает callback-кнопки «Взять в работу» / «Завершить» и обновляет статус заявки в БД.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Откройте **http://localhost:5173/** или **http://127.0.0.1:5173/**. Не запускайте `npm run dev -- --host 127.0.0.1` — npm передаёт `127.0.0.1` в Vite как **папку проекта**, из‑за этого сайт ломается. Достаточно `npm run dev` (в скрипте уже есть `vite --host`). Если **localhost** отдаёт 404, а **127.0.0.1** работает — завершите лишние процессы Node (`Диспетчер задач` → Node.js) и перезапустите dev.

Прокси Vite отправляет `/api` на `http://127.0.0.1:8000`.

## Реализовано по ТЗ

| Блок | Содержание |
|------|------------|
| Квиз | 6 шагов + экран ИИ-резюме перед формой; прогресс; Назад/Далее; localStorage; переход с лёгким `rotateY`; отправка заявки; экран успеха с номером и QR на `/lead/:id` |
| Статус заявки | `/lead/:id`, ответы и статус, polling раз в 5 с |
| JWT | `/api/auth/login`, роли `admin` / `manager`, редирект после входа |
| Менеджер | Список с фильтром по статусу, карточка: резюме, скрипт звонка (заглушка), таблица ответов, статусы, `tel:`, заметки, голосовые заметки с транскрипцией (Groq и/или Hugging Face Inference), напоминание (сохранение в БД) |
| Админ | Создание менеджеров, статистика взял/закрыл/конверсия, воронка и заявки по дням, экспорт CSV, сохранение JSON-схемы квиза (задел под Vue Flow) |
| API | Эндпоинты из ТЗ: лиды, статус, заметки, аналитика, менеджеры, quiz-schema |
| ИИ | Шаблонное резюме и скрипт звонка в `app/services/ai_text.py` (замена на LLM — точка расширения) |

## Структура каталогов

- `backend/app` — FastAPI, модели, роутеры, сервисы
- `backend/bot_worker.py` — polling Telegram
- `frontend/src` — квиз, кабинеты, API-клиент

## Следующие шаги (из приоритетов)

1. Подключить реальный LLM для резюме и скрипта.
2. Планировщик напоминаний + сообщения менеджеру в Telegram.
4. Canvas / Vue Flow в админке поверх уже сохраняемой схемы.
