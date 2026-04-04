from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models import LeadStatus, UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str
    user_id: UUID


class LoginBody(BaseModel):
    email: str
    password: str


class TelegramLinkResponse(BaseModel):
    url: str
    expires_at: datetime


class UserPublic(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole

    model_config = {"from_attributes": True}


class ManagerCreate(BaseModel):
    full_name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=6)


class ManagerStats(BaseModel):
    id: UUID
    email: str
    full_name: str
    in_progress_count: int
    completed_count: int
    conversion_percent: float


class QuizAnswers(BaseModel):
    room_type: str | None = None
    zones: list[str] = Field(default_factory=list)
    area_sqm: int | None = None
    style: str | None = None
    budget: str | None = None


class LeadCreate(BaseModel):
    name: str = Field(..., min_length=1)
    phone: str = Field(..., min_length=10)
    email: EmailStr | None = None
    comment: str | None = None
    consent: bool = False
    answers: dict[str, Any]
    session_id: str | None = None
    quiz_schema_id: int | None = None
    page_url: str | None = Field(None, max_length=2048)
    utm_source: str | None = Field(None, max_length=256)

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_none(cls, v: Any) -> Any:
        if v == "" or v is None:
            return None
        return v

    @field_validator("page_url", "utm_source", mode="before")
    @classmethod
    def normalize_optional_url_fields(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, str):
            return v
        s = v.strip()
        return s or None


class LeadCreateResponse(BaseModel):
    id: UUID
    request_number: str
    ai_summary: str
    ai_summary_client: str
    page_url: str | None = None
    utm_source: str | None = None


class LeadPublicView(BaseModel):
    id: UUID
    request_number: str
    status: LeadStatus
    answers: dict[str, Any]
    ai_summary_client: str | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuizSchemaValidateOut(BaseModel):
    ok: bool
    errors: list[str] = Field(default_factory=list)


class LeadListItem(BaseModel):
    id: UUID
    name: str
    phone: str
    room_type: str | None
    budget: str | None
    status: LeadStatus
    created_at: datetime
    assigned_manager_id: UUID | None = None
    assigned_manager_name: str | None = None
    pool_entered_at: datetime | None = None
    callback_at: datetime | None = None
    callback_note: str | None = None

    model_config = {"from_attributes": True}


class LeadDetail(BaseModel):
    id: UUID
    name: str
    phone: str
    email: str | None
    comment: str | None
    consent: bool
    answers: dict[str, Any]
    ai_summary: str | None
    ai_summary_client: str | None = None
    call_script: str | None
    status: LeadStatus
    assigned_manager_id: UUID | None
    created_at: datetime
    updated_at: datetime | None
    pool_entered_at: datetime | None = None
    callback_at: datetime | None = None
    callback_note: str | None = None
    page_url: str | None = None
    utm_source: str | None = None

    model_config = {"from_attributes": True}


class NoteOut(BaseModel):
    id: UUID
    body: str
    is_voice: bool
    created_at: datetime
    author_id: UUID | None

    model_config = {"from_attributes": True}


class LeadManagerDetail(LeadDetail):
    notes: list[NoteOut] = Field(default_factory=list)
    request_number: str


class LeadStatusPatch(BaseModel):
    """Менеджер: только завершение своей заявки { \"status\": \"completed\" }."""
    status: LeadStatus


class LeadAdminPatch(BaseModel):
    """Админ: частичное обновление (только переданные поля). assigned_manager_id: null — снять назначение."""
    status: LeadStatus | None = None
    assigned_manager_id: UUID | None = None


class LeadCallbackPatch(BaseModel):
    """Перезвонить позже: дата/время и короткий комментарий. callback_at: null — сбросить."""
    callback_at: datetime | None = None
    callback_note: str | None = Field(None, max_length=500)


class NoteCreate(BaseModel):
    text: str = Field(..., min_length=1)


class AnalyticsTrackBody(BaseModel):
    session_id: str
    event_type: str
    step_key: str | None = None
    payload: dict[str, Any] | None = None
    quiz_schema_id: int | None = None


class SummaryPreviewBody(BaseModel):
    answers: dict[str, Any]


class SummaryPreviewResponse(BaseModel):
    summary: str


class CallScriptResponse(BaseModel):
    script: str


class ReminderCreate(BaseModel):
    remind_at: datetime


class QuizSchemaBody(BaseModel):
    name: str = "default"
    schema: dict[str, Any]


class QuizSchemaOut(BaseModel):
    id: int
    name: str
    schema: dict[str, Any]
    is_active: bool
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuizSchemaListOut(BaseModel):
    id: int
    name: str
    is_active: bool
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class QuizSchemaPatch(BaseModel):
    name: str | None = None
    schema: dict[str, Any] | None = None
