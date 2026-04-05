import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"


class LeadStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=UserRole.manager)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    notes_authored: Mapped[list["Note"]] = relationship(back_populates="author")


class TelegramLinkToken(Base):
    """Одноразовая ссылка t.me/bot?start=<token> для привязки Telegram к пользователю сайта."""

    __tablename__ = "telegram_link_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_schema_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quiz_schema.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent: Mapped[bool] = mapped_column(Boolean, default=False)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    # Резюме для менеджера (звонок, CRM); без «клиентского» тона.
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Краткое резюме для клиента (экран квиза, публичная страница заявки).
    ai_summary_client: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_script: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        Enum(LeadStatus, native_enum=False, values_callable=lambda x: [e.value for e in x]),
        default=LeadStatus.pending,
    )
    assigned_manager_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Текущий заход в пул ожидания (сортировка пула); при взятии в работу обнуляется.
    pool_entered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    callback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    callback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Одноразовое напоминание в Telegram о перезвоне (сбрасывается при смене callback в API).
    callback_due_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    utm_source: Mapped[str | None] = mapped_column(String(256), nullable=True)

    notes: Mapped[list["Note"]] = relationship(back_populates="lead")
    reminders: Mapped[list["Reminder"]] = relationship(back_populates="lead")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("leads.id"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    is_voice: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="notes")
    author: Mapped["User | None"] = relationship(back_populates="notes_authored")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("leads.id"), index=True)
    manager_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lead: Mapped["Lead"] = relationship(back_populates="reminders")


class QuizSchemaRow(Base):
    __tablename__ = "quiz_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), default="default")
    schema: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_schema_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quiz_schema.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    step_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsSession(Base):
    """Последняя активность по session_id квиза (для серверных «дропов» без заявки)."""

    __tablename__ = "analytics_sessions"

    quiz_schema_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quiz_schema.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_step_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
