"""Transkripsi untuk pra-cek: API OpenAI-compatible atau faster-whisper (open source) lokal."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_whisper_model = None


@dataclass
class SttResult:
    text: str | None
    failure: str | None = None


def _local_http_stt() -> bool:
    base = settings.stt_base_url.lower()
    return "localhost" in base or "127.0.0.1" in base or "[::1]" in base


def is_configured() -> bool:
    if not settings.stt_enabled:
        return False
    engine = (settings.stt_engine or "openai").lower()
    if engine == "faster_whisper":
        return True
    if settings.stt_api_key:
        return True
    return _local_http_stt()


def engine_label() -> str:
    engine = (settings.stt_engine or "openai").lower()
    if engine == "faster_whisper":
        return f"faster-whisper ({settings.stt_whisper_model})"
    if _local_http_stt():
        return "STT lokal (OpenAI-compatible)"
    return "STT cloud"


def _failure_from_status(status: int) -> str:
    if status == 401:
        return "stt_auth"
    if status == 429:
        return "stt_quota"
    if status >= 400:
        return "stt_api"
    return "stt_api"


def _ext_from_content_type(content_type: str) -> str:
    if "webm" in content_type:
        return "webm"
    if "ogg" in content_type:
        return "ogg"
    if "mp4" in content_type:
        return "mp4"
    return "wav"


def _load_whisper():
    """Muat model sekali per proses (unduhan pertama dari Hugging Face bisa memakan waktu)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel

        compute = "int8" if settings.stt_whisper_device == "cpu" else "float16"
        _whisper_model = WhisperModel(settings.stt_whisper_model, device=settings.stt_whisper_device, compute_type=compute)
    return _whisper_model


async def preload() -> None:
    """Panaskan model saat server menyala agar setoran pertama tidak menunggu unduhan. Gagal tidak fatal."""
    if not (settings.stt_enabled and (settings.stt_engine or "").lower() == "faster_whisper"):
        return
    try:
        await asyncio.to_thread(_load_whisper)
        logger.info("faster-whisper siap (%s)", settings.stt_whisper_model)
    except Exception as e:  # noqa: BLE001
        logger.warning("faster-whisper belum siap: %s: %s", type(e).__name__, e)


def _transcribe_faster_whisper_sync(audio: bytes, content_type: str, reference_hint: str | None = None) -> SttResult:
    try:
        _load_whisper()
    except ImportError:
        return SttResult(None, "stt_not_installed")

    ext = _ext_from_content_type(content_type)
    try:
        fd, path_str = tempfile.mkstemp(suffix=f".{ext}")
        path = Path(path_str)
        try:
            with open(fd, "wb") as tmp:
                tmp.write(audio)
            prompt = (reference_hint or "").strip()[:220] or None
            segments, _ = _whisper_model.transcribe(
                str(path),
                language="ar",
                beam_size=5,
                vad_filter=False,
                initial_prompt=prompt,
                condition_on_previous_text=False,
            )
            text = " ".join(s.text.strip() for s in segments if s.text.strip())
        finally:
            path.unlink(missing_ok=True)
        if text:
            return SttResult(text, None)
        return SttResult(None, "stt_empty")
    except Exception as e:
        logger.warning("faster-whisper gagal: %s: %s", type(e).__name__, e)
        if "metadata_errors" in str(e) or isinstance(e, TypeError):
            return SttResult(None, "stt_av_version")
        return SttResult(None, "stt_api")


async def _transcribe_openai_http(audio: bytes, content_type: str) -> SttResult:
    ext = _ext_from_content_type(content_type)
    api_key = settings.stt_api_key or "local"
    try:
        async with httpx.AsyncClient(timeout=settings.stt_timeout_seconds) as client:
            r = await client.post(
                f"{settings.stt_base_url.rstrip('/')}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data={"model": settings.stt_model, "language": "ar", "response_format": "json", "temperature": "0"},
                files={"file": (f"rec.{ext}", audio, content_type)},
            )
        if r.status_code >= 400:
            code = _failure_from_status(r.status_code)
            logger.warning("STT HTTP %s -> %s", r.status_code, code)
            return SttResult(None, code)
        text = r.json().get("text")
        if isinstance(text, str) and text.strip():
            return SttResult(text.strip(), None)
        return SttResult(None, "stt_empty")
    except httpx.HTTPError as e:
        logger.warning("STT jaringan gagal: %s", type(e).__name__)
        return SttResult(None, "stt_network")
    except Exception as e:
        logger.warning("STT gagal: %s", type(e).__name__)
        return SttResult(None, "stt_api")


async def transcribe(
    audio: bytes,
    content_type: str = "audio/webm",
    reference_hint: str | None = None,
) -> SttResult:
    if not is_configured():
        return SttResult(None, "disabled")
    if not audio:
        return SttResult(None, "empty_audio")
    engine = (settings.stt_engine or "openai").lower()
    if engine == "faster_whisper":
        return await asyncio.to_thread(_transcribe_faster_whisper_sync, audio, content_type, reference_hint)
    return await _transcribe_openai_http(audio, content_type)


async def transcribe_text(audio: bytes, content_type: str = "audio/webm") -> str | None:
    return (await transcribe(audio, content_type)).text
