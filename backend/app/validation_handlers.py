"""Русские сообщения для ошибок валидации тела запроса (422)."""

from __future__ import annotations

from typing import Any

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _field_label_ru(loc: tuple[Any, ...]) -> str:
    if not loc:
        return "Данные"
    tail = str(loc[-1])
    return {
        "name": "Имя",
        "phone": "Телефон",
        "email": "Электронная почта",
        "comment": "Комментарий",
        "consent": "Согласие",
        "answers": "Ответы квиза",
        "password": "Пароль",
        "full_name": "ФИО",
        "remind_at": "Время напоминания",
        "callback_at": "Время перезвона",
        "callback_note": "Комментарий к перезвону",
        "status": "Статус",
        "text": "Текст",
        "schema": "Схема квиза",
        "session_id": "Сессия",
        "quiz_schema_id": "Квиз",
        "page_url": "Адрес страницы",
        "utm_source": "UTM",
        "is_active": "Доступ к аккаунту",
    }.get(tail, tail)


def _message_ru(err: dict[str, Any]) -> str:
    t = str(err.get("type") or "")
    ctx = err.get("ctx") or {}
    msg = str(err.get("msg") or "")

    if msg.startswith("Value error, "):
        return msg[len("Value error, ") :].strip()

    if t == "missing":
        return "обязательно для заполнения"
    if t == "string_too_short":
        n = ctx.get("min_length", "?")
        return f"слишком коротко (нужно минимум {n} символов)"
    if t == "string_too_long":
        n = ctx.get("max_length", "?")
        return f"слишком длинно (максимум {n} символов)"
    if t in ("bool_parsing", "bool_type"):
        return "ожидается значение да/нет"
    if t == "int_parsing":
        return "ожидается целое число"
    if t == "float_parsing":
        return "ожидается число"
    if "email" in t or "email" in msg.lower():
        return "некорректный адрес электронной почты"
    if t == "dict_type":
        return "ожидается объект"
    if t == "list_type":
        return "ожидается список"
    if t == "uuid_parsing":
        return "некорректный идентификатор"
    if t == "enum":
        return "недопустимое значение из списка"
    if t in ("json_invalid", "json_type"):
        return "некорректный JSON"

    if msg and not msg.isascii():
        return msg.strip()
    if msg:
        return "некорректное значение"
    return "некорректное значение"


def format_validation_errors(errors: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for err in errors:
        loc = tuple(err.get("loc") or ())
        skip_header = len(loc) >= 1 and str(loc[0]) in ("body", "query", "path", "header")
        label = _field_label_ru(loc[1:] if skip_header and len(loc) > 1 else loc)
        parts.append(f"{label}: {_message_ru(err)}")
    return "; ".join(parts) if parts else "Проверьте данные формы."


async def request_validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    text = format_validation_errors(exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": text},
    )
