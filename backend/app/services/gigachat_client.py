"""Клиент OAuth и chat/completions GigaChat (Сбер). Секреты только из настроек окружения."""

from __future__ import annotations

import base64
import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _resolve_credentials() -> str | None:
    raw = (settings.GIGACHAT_CREDENTIALS or "").strip()
    if raw:
        return raw
    cid = (settings.GIGACHAT_CLIENT_ID or "").strip()
    sec = (settings.GIGACHAT_CLIENT_SECRET or "").strip()
    if cid and sec:
        return base64.b64encode(f"{cid}:{sec}".encode()).decode()
    return None


class GigaChatClient:
    def __init__(self) -> None:
        cred = _resolve_credentials()
        if not cred:
            raise ValueError("GigaChat: задайте GIGACHAT_CREDENTIALS или GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET")
        self._credentials = cred
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._verify = settings.GIGACHAT_VERIFY_SSL

    @staticmethod
    def _rquid() -> str:
        return str(uuid.uuid4())

    def _fetch_oauth(self, data: dict[str, str]) -> bool:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Authorization": f"Basic {self._credentials}",
            "RqUID": self._rquid(),
        }
        t = httpx.Timeout(
            connect=12.0,
            read=float(settings.GIGACHAT_OAUTH_TIMEOUT_SEC),
            write=12.0,
            pool=5.0,
        )
        try:
            with httpx.Client(verify=self._verify, timeout=t) as client:
                r = client.post(settings.GIGACHAT_OAUTH_URL, headers=headers, data=data)
                r.raise_for_status()
                token_data = r.json()
        except Exception as e:
            logger.warning("GigaChat OAuth error: %s", e)
            return False

        self._access_token = token_data.get("access_token")
        self._refresh_token = token_data.get("refresh_token")
        expires_in = int(token_data.get("expires_in") or 1800)
        # запас 5 минут до истечения
        self._token_expires_at = datetime.now() + timedelta(seconds=max(120, expires_in - 300))
        return bool(self._access_token)

    def _ensure_token(self) -> bool:
        if (
            self._access_token
            and self._token_expires_at
            and datetime.now() < self._token_expires_at
        ):
            return True

        with self._lock:
            if (
                self._access_token
                and self._token_expires_at
                and datetime.now() < self._token_expires_at
            ):
                return True

            if self._refresh_token:
                if self._fetch_oauth(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    }
                ):
                    return True
                self._refresh_token = None

            return self._fetch_oauth({"scope": settings.GIGACHAT_SCOPE})

    def chat_completions(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        read_timeout_sec: float | None = None,
    ) -> dict[str, Any] | None:
        if not self._ensure_token():
            return None

        url = f"{settings.GIGACHAT_BASE_URL.rstrip('/')}/chat/completions"
        body: dict[str, Any] = {
            "model": model or settings.GIGACHAT_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._access_token}",
        }

        read_to = float(read_timeout_sec if read_timeout_sec is not None else settings.GIGACHAT_TIMEOUT_SEC)
        chat_timeout = httpx.Timeout(connect=12.0, read=read_to, write=12.0, pool=5.0)

        def do_post() -> httpx.Response:
            with httpx.Client(verify=self._verify, timeout=chat_timeout) as client:
                return client.post(url, headers=headers, json=body)

        try:
            resp = do_post()
            if resp.status_code == 401:
                with self._lock:
                    self._access_token = None
                if self._ensure_token():
                    headers["Authorization"] = f"Bearer {self._access_token}"
                    resp = do_post()
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("GigaChat chat/completions error: %s", e)
            return None

    def complete_system_user(
        self,
        system: str,
        user: str,
        *,
        read_timeout_sec: float | None = None,
    ) -> str | None:
        data = self.chat_completions(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            read_timeout_sec=read_timeout_sec,
        )
        if not data:
            return None
        try:
            choices = data.get("choices")
            if not choices:
                return None
            msg = choices[0].get("message") or {}
            text = msg.get("content")
            return str(text).strip() if text else None
        except (IndexError, KeyError, TypeError):
            return None


_client: GigaChatClient | None = None
_client_lock = threading.Lock()


def get_gigachat_client() -> GigaChatClient | None:
    """Ленивый синглтон; None если учётные данные не заданы."""
    global _client
    if _resolve_credentials() is None:
        return None
    with _client_lock:
        if _client is None:
            try:
                _client = GigaChatClient()
            except ValueError:
                return None
        return _client
