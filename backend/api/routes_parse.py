"""POST /api/parse and POST /api/upload."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from api.errors import make_error
from api.store import ParsedFileStore
from config import MusicSource
from parser.midi_parser import ParseError, parse_midi_file
from parser.track_classifier import classify_tracks
from search.base import BaseMusicSearcher
from search.bilibili import BilibiliSearcher
from search.bitmidi import BitMidiSearcher
from search.freemidi import FreeMidiSearcher
from search.musescore import MuseScoreSearcher
from utils.cache import cache_path_for_url, ensure_cache_dir, is_cached, DEFAULT_CACHE_DIR
from utils.downloader import DownloadError, download_to_path

router = APIRouter(prefix="/api", tags=["parse"])
_LOG = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    result_id: str
    download_url: str
    title: str
    source: MusicSource | None = None  # which platform produced this URL


def get_store() -> ParsedFileStore:  # overridden via main.app
    raise RuntimeError("get_store must be overridden by main.py")


# Source → searcher class. Used to dispatch downloads through a
# searcher-specific fetcher (some sites need cookies / multi-step flows).
_SEARCHER_BY_SOURCE: dict[MusicSource, type[BaseMusicSearcher]] = {
    MusicSource.FREEMIDI: FreeMidiSearcher,
    MusicSource.BITMIDI: BitMidiSearcher,
    MusicSource.MUSESCORE: MuseScoreSearcher,
    MusicSource.BILIBILI: BilibiliSearcher,
}


@router.post("/parse")
async def parse(
    payload: ParseRequest,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    target = cache_path_for_url(payload.download_url)
    if not is_cached(payload.download_url):
        try:
            await _fetch_via_searcher(
                payload.download_url, target, source=payload.source
            )
        except DownloadError as exc:
            raise make_error("DOWNLOAD_FAILED", detail=str(exc))
    return parse_and_save_midi(target, payload.title, store)


async def _fetch_via_searcher(
    url: str,
    target: Path,
    *,
    source: MusicSource | None,
) -> None:
    """Dispatch to a source-specific fetcher when the platform requires
    it (e.g. FreeMIDI's session-cookie + Referer dance). Falls through
    to the generic downloader otherwise."""
    if source is not None:
        searcher_cls = _SEARCHER_BY_SOURCE.get(source)
        if searcher_cls is not None:
            searcher = searcher_cls()
            await searcher.fetch_to_path(url, target)
            return
    await download_to_path(url, target)


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
    return parse_and_save_midi(target, title, store)


def parse_and_save_midi(path: Path, title: str, store: ParsedFileStore) -> dict:
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
