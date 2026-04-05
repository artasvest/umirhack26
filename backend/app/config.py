from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Всегда backend/.env (рядом с каталогом app), независимо от cwd при запуске uvicorn.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    # Только .env — иначе значения из закоммиченного .env.example (например Postgres) ломают локальный запуск.
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.is_file() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Только PostgreSQL + asyncpg (см. app/database.py). Реальные учётные данные — в .env.
    DATABASE_URL: str = "postgresql+asyncpg://umir_user:0607078219@db:5432/umir_db"
    JWT_SECRET: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    TELEGRAM_BOT_TOKEN: str = ""
    # Имя бота без @ — для ссылок https://t.me/<username>?start=...
    TELEGRAM_BOT_USERNAME: str = ""
    TELEGRAM_MANAGER_CHAT_ID: str = ""

    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    ADMIN_EMAIL: str = "admin@studio.local"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_NAME: str = "Администратор"

    FRONTEND_PUBLIC_URL: str = "http://localhost:5173"

    # Сессия без заявки и без активности дольше — «дроп» на последнем шаге (см. analytics_sessions).
    ANALYTICS_DROP_IDLE_MINUTES: int = 30

    # Сколько заявок «в работе» менеджер может взять из общего пула сам (админ может назначить сверх).
    MANAGER_MAX_ACTIVE_LEADS: int = 5

    # GigaChat: Base64(client_id:client_secret) из личного кабинета ИЛИ пара id/secret ниже.
    GIGACHAT_CREDENTIALS: str = ""
    GIGACHAT_CLIENT_ID: str = ""
    GIGACHAT_CLIENT_SECRET: str = ""
    GIGACHAT_SCOPE: str = "GIGACHAT_API_PERS"
    GIGACHAT_BASE_URL: str = "https://gigachat.devices.sberbank.ru/api/v1"
    GIGACHAT_OAUTH_URL: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    GIGACHAT_MODEL: str = "GigaChat"
    GIGACHAT_VERIFY_SSL: bool = True
    GIGACHAT_TIMEOUT_SEC: float = 60.0
    # Отдельно для chat/completions (резюме), чтобы не висеть минуту на запросе.
    GIGACHAT_SUMMARY_TIMEOUT_SEC: float = 20.0
    GIGACHAT_OAUTH_TIMEOUT_SEC: float = 25.0

    # Транскрипция голосовых заметок (Whisper). Ключ Groq — для api.groq.com; для Hugging Face нужен HF-токен.
    GROQ_API_KEY: str = ""
    GROQ_TRANSCRIPTION_MODEL: str = "whisper-large-v3-turbo"
    GROQ_TRANSCRIPTION_TIMEOUT_SEC: float = 120.0

    HUGGINGFACE_API_TOKEN: str = ""
    HUGGINGFACE_WHISPER_URL: str = "https://api-inference.huggingface.co/models/openai/whisper-large-v3-turbo"
    HUGGINGFACE_TRANSCRIPTION_TIMEOUT_SEC: float = 120.0
    # auto: сначала Groq при наличии ключа, иначе HF; groq | huggingface — только выбранный провайдер
    WHISPER_PROVIDER: str = "auto"


settings = Settings()
