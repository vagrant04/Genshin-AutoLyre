"""Audio → MIDI → parsed-MIDI pipeline orchestrator.

Single entry point: `run_transcribe_pipeline()`. Inputs are an audio
source, a transcribe function (so tests can substitute the real Basic
Pitch call), the two stores, and a request object. Side effects:
  - Updates audio_store as the job progresses.
  - Caches the downloaded audio under cache_root/audio/.
  - Caches the transcribed MIDI under cache_root/midi/transcribed/.
  - Inserts the parsed MIDI into parse_store.
  - On any failure, marks the job ERROR with a human-readable message.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol

from audio.exceptions import (
    AudioError,
    SourceUnavailable,
    TranscriptionError,
)
from audio.store import AudioFileStore, JobStage
from api.routes_parse import parse_and_save_midi
from api.store import ParsedFileStore

_LOG = logging.getLogger(__name__)


@dataclass
class TranscribeRequest:
    """Inputs needed by the orchestrator.

    Either `canonical_url` (for source-fetched audio) or
    `local_audio_path` (for uploaded audio) must be set.
    """
    title: str
    onset_threshold: float
    min_note_length_ms: int
    canonical_url: Optional[str] = None
    local_audio_path: Optional[Path] = None


class _SourceLike(Protocol):
    async def fetch_to_path(self, url: str, target: Path) -> Any: ...


TranscribeFn = Callable[..., Awaitable[Path]]


async def run_transcribe_pipeline(
    *,
    job_token: str,
    request: TranscribeRequest,
    source: _SourceLike,
    transcribe_fn: TranscribeFn,
    parse_store: ParsedFileStore,
    audio_store: AudioFileStore,
    cache_root: Path,
) -> None:
    audio_dir = cache_root / "audio"
    midi_dir = cache_root / "midi" / "transcribed"
    audio_dir.mkdir(parents=True, exist_ok=True)
    midi_dir.mkdir(parents=True, exist_ok=True)

    try:
        audio_path = await _resolve_audio(
            request=request,
            source=source,
            audio_dir=audio_dir,
            audio_store=audio_store,
            job_token=job_token,
        )

        audio_store.update(job_token, stage=JobStage.TRANSCRIBING)
        midi_path = _midi_cache_path(
            request=request,
            audio_path=audio_path,
            midi_dir=midi_dir,
        )
        if not midi_path.is_file():
            await transcribe_fn(
                audio_path,
                midi_path,
                onset_threshold=request.onset_threshold,
                min_note_length_ms=request.min_note_length_ms,
            )

        audio_store.update(job_token, stage=JobStage.PARSING)
        parsed = parse_and_save_midi(midi_path, request.title, parse_store)
        audio_store.update(
            job_token,
            stage=JobStage.DONE,
            parse_token=parsed["file_token"],
        )
    except SourceUnavailable as exc:
        _LOG.warning("audio job %s SOURCE_UNAVAILABLE: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except TranscriptionError as exc:
        _LOG.warning("audio job %s TRANSCRIPTION_FAILED: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except AudioError as exc:
        _LOG.warning("audio job %s AUDIO_ERROR: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("audio job %s unexpected failure", job_token)
        audio_store.update(
            job_token, stage=JobStage.ERROR, error=f"unexpected: {exc}"
        )


async def _resolve_audio(
    *,
    request: TranscribeRequest,
    source: _SourceLike,
    audio_dir: Path,
    audio_store: AudioFileStore,
    job_token: str,
) -> Path:
    if request.local_audio_path is not None:
        return request.local_audio_path

    if not request.canonical_url:
        raise AudioError("transcribe request has neither url nor local audio")

    audio_path = _audio_cache_path(request.canonical_url, audio_dir)
    if audio_path.is_file():
        return audio_path

    audio_store.update(job_token, stage=JobStage.DOWNLOADING)
    await source.fetch_to_path(request.canonical_url, audio_path)
    return audio_path


def _audio_cache_path(canonical_url: str, audio_dir: Path) -> Path:
    h = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    return audio_dir / f"{h}.audio"


def _midi_cache_path(
    *,
    request: TranscribeRequest,
    audio_path: Path,
    midi_dir: Path,
) -> Path:
    """Cache key includes URL/local path AND transcription params."""
    seed = f"{request.canonical_url or audio_path}::"
    seed += f"{request.onset_threshold}::{request.min_note_length_ms}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return midi_dir / f"{h}.mid"
