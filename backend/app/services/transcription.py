"""Транскрипция голосовых заметок: Groq (OpenAI-совместимый Whisper) или Hugging Face Inference API."""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _guess_mime(filename: str) -> str | None:
    if not filename:
        return None
    mt, _ = mimetypes.guess_type(filename)
    return mt


def _parse_openai_style_transcription(data: Any) -> str | None:
    if isinstance(data, dict) and "text" in data:
        t = data.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
    return None


def _parse_hf_transcription(data: Any) -> str | None:
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(data, dict):
        t = data.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
        # Некоторые пайплайны отдают chunks
        chunks = data.get("chunks")
        if isinstance(chunks, list) and chunks:
            parts: list[str] = []
            for c in chunks:
                if isinstance(c, dict) and isinstance(c.get("text"), str):
                    parts.append(c["text"])
            if parts:
                return " ".join(parts).strip()
    return None


async def transcribe_with_groq(content: bytes, filename: str) -> str | None:
    key = (settings.GROQ_API_KEY or "").strip()
    if not key:
        return None
    name = filename or "audio.webm"
    mime = _guess_mime(name) or "application/octet-stream"
    model = (settings.GROQ_TRANSCRIPTION_MODEL or "whisper-large-v3-turbo").strip()
    timeout = settings.GROQ_TRANSCRIPTION_TIMEOUT_SEC
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            files = {"file": (name, io.BytesIO(content), mime)}
            data = {"model": model}
            r = await client.post(
                GROQ_TRANSCRIPT_URL,
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=data,
            )
            r.raise_for_status()
            ct = (r.headers.get("content-type") or "").lower()
            if "application/json" in ct:
                parsed = _parse_openai_style_transcription(r.json())
                if parsed:
                    return parsed
            text = r.text.strip()
            return text if text else None
    except httpx.HTTPStatusError as e:
        logger.warning("Groq transcription HTTP %s: %s", e.response.status_code, e.response.text[:500])
    except Exception as e:
        logger.warning("Groq transcription failed: %s", e)
    return None


async def transcribe_with_huggingface(content: bytes, filename: str) -> str | None:
    token = (settings.HUGGINGFACE_API_TOKEN or "").strip()
    if not token:
        return None
    url = (settings.HUGGINGFACE_WHISPER_URL or "").strip()
    if not url:
        return None
    mime = _guess_mime(filename or "") or "application/octet-stream"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": mime}
    timeout = settings.HUGGINGFACE_TRANSCRIPTION_TIMEOUT_SEC
    backoff = (2, 5, 10)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(4):
                if attempt > 0:
                    await asyncio.sleep(backoff[attempt - 1])
                r = await client.post(url, headers=headers, content=content)
                if r.status_code == 503:
                    logger.info("HF Whisper 503 (model loading?), попытка %s", attempt + 1)
                    continue
                r.raise_for_status()
                ct = (r.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    return _parse_hf_transcription(r.json())
                text = r.text.strip()
                return text if text else None
    except httpx.HTTPStatusError as e:
        logger.warning("Hugging Face transcription HTTP %s: %s", e.response.status_code, e.response.text[:500])
    except Exception as e:
        logger.warning("Hugging Face transcription failed: %s", e)
    return None


async def transcribe_audio(content: bytes, filename: str) -> str | None:
    """
    Провайдер: WHISPER_PROVIDER=auto|groq|huggingface.
    Ключ Groq не подходит для api-inference.huggingface.co — для HF нужен токен с huggingface.co/settings/tokens.
    """
    mode = (settings.WHISPER_PROVIDER or "auto").strip().lower()
    has_groq = bool((settings.GROQ_API_KEY or "").strip())
    has_hf = bool((settings.HUGGINGFACE_API_TOKEN or "").strip())

    if mode == "groq":
        return await transcribe_with_groq(content, filename) if has_groq else None
    if mode in ("huggingface", "hf"):
        return await transcribe_with_huggingface(content, filename) if has_hf else None

    # auto
    if has_groq:
        text = await transcribe_with_groq(content, filename)
        if text:
            return text
    if has_hf:
        return await transcribe_with_huggingface(content, filename)
    return None
