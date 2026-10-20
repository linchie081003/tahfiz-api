"""Transkripsi audio lewat API pihak ketiga (kompatibel OpenAI /audio/transcriptions).

Hanya dipanggil bila STT_ENABLED dan orang tua sudah memberi persetujuan keluarga.
Gagal/timeout -> None (pra-cek dinyatakan "tidak tersedia", bukan nilai palsu).
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Aktif bila STT_ENABLED. Kunci API opsional (server Whisper sendiri biasanya tanpa kunci)."""
    return bool(settings.stt_enabled)


async def transcribe(audio: bytes, content_type: str = "audio/webm") -> str | None:
    if not is_configured() or not audio:
        return None
    ext = "webm" if "webm" in content_type else "ogg" if "ogg" in content_type else "mp4" if "mp4" in content_type else "wav"
    headers = {"Authorization": f"Bearer {settings.stt_api_key}"} if settings.stt_api_key else {}
    try:
        async with httpx.AsyncClient(timeout=settings.stt_timeout_seconds) as client:
            r = await client.post(
                f"{settings.stt_base_url.rstrip('/')}/audio/transcriptions",
                headers=headers,
                data={"model": settings.stt_model, "language": "ar", "response_format": "json", "temperature": "0"},
                files={"file": (f"rec.{ext}", audio, content_type)},
            )
        r.raise_for_status()
        text = r.json().get("text")
        return text.strip() if isinstance(text, str) and text.strip() else None
    except Exception as e:  # jaringan, kuota, format — jangan bocorkan detail ke pengguna
        logger.warning("STT gagal: %s", type(e).__name__)
        return None
