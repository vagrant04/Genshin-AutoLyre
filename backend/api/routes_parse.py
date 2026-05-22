"""POST /api/parse and POST /api/upload."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from api.errors import make_error
from api.store import ParsedFileStore
from parser.midi_parser import ParseError, parse_midi_file
from parser.track_classifier import classify_tracks
from utils.cache import cache_path_for_url, ensure_cache_dir, is_cached, DEFAULT_CACHE_DIR
from utils.downloader import DownloadError, download_to_path

router = APIRouter(prefix="/api", tags=["parse"])
_LOG = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    result_id: str
    download_url: str
    title: str


def get_store() -> ParsedFileStore:  # overridden via main.app
    raise RuntimeError("get_store must be overridden by main.py")


@router.post("/parse")
async def parse(
    payload: ParseRequest,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    target = cache_path_for_url(payload.download_url)
    if not is_cached(payload.download_url):
        try:
            await download_to_path(payload.download_url, target)
        except DownloadError as exc:
            raise make_error("DOWNLOAD_FAILED", detail=str(exc))
    return _parse_and_save(target, payload.title, store)


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith((".mid", ".midi")):
        raise make_error("INVALID_FILE_TYPE")

    ensure_cache_dir(DEFAULT_CACHE_DIR)
    target = DEFAULT_CACHE_DIR / f"upload_{uuid.uuid4().hex}.mid"
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise make_error("FILE_TOO_LARGE")
    target.write_bytes(contents)
    title = Path(filename).stem
    return _parse_and_save(target, title, store)


def _parse_and_save(path: Path, title: str, store: ParsedFileStore) -> dict:
    try:
        parsed = parse_midi_file(path)
    except ParseError as exc:
        raise make_error("PARSE_FAILED", detail=str(exc))
    track_infos = classify_tracks(parsed)
    token = store.save(parsed, title, track_infos=track_infos)
    return {
        "file_token": token,
        "title": title,
        "bpm": parsed.bpm,
        "ticks_per_beat": parsed.ticks_per_beat,
        "tracks": [t.model_dump(mode="json") for t in track_infos],
    }
