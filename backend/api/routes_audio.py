"""GET /api/audio/search, POST /api/audio/transcribe, GET /api/audio/jobs/{token}.

The transcribe route returns immediately with a job token; the actual
work runs as a FastAPI BackgroundTask. The frontend polls
/api/audio/jobs/{token} until stage = "done" or "error".
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    UploadFile,
)
from pydantic import BaseModel

from api.errors import make_error
from api.routes_parse import get_store as get_parse_store
from api.store import ParsedFileStore
from audio.pipeline import TranscribeRequest, run_transcribe_pipeline
from audio.sources.base import AbstractAudioSource
from audio.sources.bilibili import BilibiliSource
from audio.sources.qqmusic import QQMusicSource
from audio.sources.youtube import YouTubeSource
from audio.store import AudioFileStore, JobStage
from audio.transcriber import (
    DEFAULT_MIN_NOTE_LENGTH_MS,
    SENSITIVITY_PRESETS,
    transcribe as default_transcribe,
)

router = APIRouter(prefix="/api/audio", tags=["audio"])
_LOG = logging.getLogger(__name__)


PlatformParam = Literal["youtube", "bilibili", "qqmusic"]
SensitivityParam = Literal["low", "medium", "high"]


class JobStatusResponse(BaseModel):
    job_token: str
    stage: JobStage
    error: Optional[str] = None
    parse_token: Optional[str] = None


def get_audio_cache_root() -> Path:
    return Path("/tmp/genshin_lyre")


def get_audio_store() -> AudioFileStore:
    raise RuntimeError("get_audio_store must be overridden by main.py")


def get_transcribe_fn():
    return default_transcribe


_SOURCE_BY_PLATFORM: dict[str, type[AbstractAudioSource]] = {
    "youtube": YouTubeSource,
    "bilibili": BilibiliSource,
    "qqmusic": QQMusicSource,
}


def get_source_for_platform(platform: PlatformParam) -> AbstractAudioSource:
    return _SOURCE_BY_PLATFORM[platform]()


def get_source_for_url(url: str) -> AbstractAudioSource:
    platform = _platform_from_url(url)
    if platform is None:
        raise make_error("INVALID_AUDIO_URL", detail=url)
    return _SOURCE_BY_PLATFORM[platform]()


def _platform_from_url(url: str) -> Optional[PlatformParam]:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return None
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "bilibili.com" in host:
        return "bilibili"
    if "qq.com" in host:
        return "qqmusic"
    return None


@router.get("/search")
async def audio_search(
    q: Annotated[str, Query(min_length=1)],
    platform: Annotated[PlatformParam, Query()],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    source: AbstractAudioSource = Depends(get_source_for_platform),
) -> dict:
    candidates = await source.search(q, limit=limit)
    return {
        "query": q,
        "platform": platform,
        "total": len(candidates),
        "candidates": [c.model_dump(mode="json") for c in candidates],
    }


@router.post("/transcribe")
async def audio_transcribe(
    background_tasks: BackgroundTasks,
    request: Request,
    input_mode: Annotated[Literal["url", "upload", "candidate"], Form()] = "url",
    file: Annotated[Optional[UploadFile], File()] = None,
    url: Annotated[Optional[str], Form()] = None,
    canonical_url: Annotated[Optional[str], Form()] = None,
    source_param: Annotated[Optional[PlatformParam], Form(alias="source")] = None,
    title: Annotated[Optional[str], Form()] = None,
    onset_sensitivity: Annotated[SensitivityParam, Form()] = "medium",
    min_note_ms: Annotated[int, Form(ge=10, le=2000)] = DEFAULT_MIN_NOTE_LENGTH_MS,
    parse_store: ParsedFileStore = Depends(get_parse_store),
    audio_store: AudioFileStore = Depends(get_audio_store),
    transcribe_fn=Depends(get_transcribe_fn),
    cache_root: Path = Depends(get_audio_cache_root),
) -> dict:
    source: Optional[AbstractAudioSource] = None
    local_audio_path: Optional[Path] = None
    canonical: Optional[str] = None
    resolved_title: str = title or "Untitled"

    # Honor app.dependency_overrides so tests can inject stub sources.
    overrides = request.app.dependency_overrides
    resolve_url = overrides.get(get_source_for_url, get_source_for_url)
    resolve_platform = overrides.get(get_source_for_platform, get_source_for_platform)

    if input_mode == "url":
        if not url:
            raise make_error("INVALID_AUDIO_URL", detail="missing url")
        source = resolve_url(url)
        canonical = url
    elif input_mode == "candidate":
        if not (canonical_url and source_param):
            raise make_error(
                "INVALID_AUDIO_URL",
                detail="candidate mode requires source + canonical_url",
            )
        source = resolve_platform(source_param)
        canonical = canonical_url
    elif input_mode == "upload":
        if not file:
            raise make_error("INVALID_FILE_TYPE", detail="missing file")
        filename = file.filename or ""
        if not filename.lower().endswith((".mp3", ".m4a", ".mp4", ".wav", ".aac")):
            raise make_error("INVALID_FILE_TYPE")
        cache_root.mkdir(parents=True, exist_ok=True)
        upload_path = cache_root / "audio" / f"upload_{uuid.uuid4().hex}.m4a"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        # Stream the upload in chunks so a malicious >>50MB file is
        # rejected without first being held entirely in memory.
        max_bytes = 50 * 1024 * 1024
        total = 0
        with upload_path.open("wb") as out_fh:
            while True:
                chunk = await file.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    out_fh.close()
                    upload_path.unlink(missing_ok=True)
                    raise make_error("AUDIO_TOO_LARGE")
                out_fh.write(chunk)
        local_audio_path = upload_path
        resolved_title = title or Path(filename).stem
    else:
        raise make_error("INVALID_AUDIO_URL", detail=f"unknown input_mode: {input_mode}")

    onset_threshold = SENSITIVITY_PRESETS[onset_sensitivity]

    request = TranscribeRequest(
        title=resolved_title,
        onset_threshold=onset_threshold,
        min_note_length_ms=min_note_ms,
        canonical_url=canonical,
        local_audio_path=local_audio_path,
    )
    job_token = audio_store.create_job()

    if source is None:
        source = YouTubeSource()  # never invoked in upload mode

    # Note: FastAPI BackgroundTasks continue running even if the client
    # disconnects mid-transcription. The audio_store entry persists for
    # the process lifetime; cache files persist until the cache dir is
    # manually cleared. For an MVP / personal-use tool this is fine.
    background_tasks.add_task(
        run_transcribe_pipeline,
        job_token=job_token,
        request=request,
        source=source,
        transcribe_fn=transcribe_fn,
        parse_store=parse_store,
        audio_store=audio_store,
        cache_root=cache_root,
    )
    return {"job_token": job_token}


@router.get("/jobs/{job_token}")
async def audio_job_status(
    job_token: str,
    audio_store: AudioFileStore = Depends(get_audio_store),
) -> dict:
    try:
        job = audio_store.get(job_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND", detail=job_token)
    return JobStatusResponse(
        job_token=job_token,
        stage=job.stage,
        error=job.error,
        parse_token=job.parse_token,
    ).model_dump(mode="json")
