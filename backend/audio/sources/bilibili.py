"""Bilibili audio source via yt-dlp's BilibiliExtractor."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)

# Bilibili rejects requests without a browser-shaped UA + Referer
# (HTTP 412). yt-dlp's extractor doesn't set these by default.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


def _default_factory(params: dict[str, Any]):
    import yt_dlp  # noqa: WPS433
    return yt_dlp.YoutubeDL(params)


class BilibiliSource(AbstractAudioSource):
    source = AudioSourceKey.BILIBILI

    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_factory,
    ) -> None:
        self._factory = ydl_factory

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        # Note: NO extract_flat. Flat extraction returns numeric AVIDs
        # without titles/thumbnails; full extraction returns BVIDs and
        # rich metadata. Costs an HTTP call per video but the search
        # is small (typically ≤5 results) so it's acceptable.
        params = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "http_headers": _BROWSER_HEADERS,
            "socket_timeout": 30,
        }
        info = await asyncio.to_thread(
            self._extract, params, f"bilisearch{limit}:{query}", False
        )
        entries = (info or {}).get("entries") or []
        out: list[AudioCandidate] = []
        for e in entries[:limit]:
            if not isinstance(e, dict):
                continue
            bvid = e.get("id") or ""
            if not bvid:
                continue
            # Build canonical https URL from the BVID rather than
            # trusting webpage_url, which yt-dlp sometimes returns as
            # the legacy http://www.bilibili.com/video/avNNN form.
            canonical_url = f"https://www.bilibili.com/video/{bvid}"
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=bvid,
                    title=str(e.get("title") or "Untitled"),
                    artist=e.get("uploader"),
                    duration_seconds=int(e["duration"]) if e.get("duration") else None,
                    thumbnail_url=e.get("thumbnail"),
                    canonical_url=canonical_url,
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.parent.mkdir(parents=True, exist_ok=True)
        params: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio*/best",
            "outtmpl": str(target),
            "noplaylist": True,
            "http_headers": dict(_BROWSER_HEADERS),
            "socket_timeout": 60,
        }
        sessdata = os.environ.get("BILI_SESSDATA")
        if sessdata:
            # Merge instead of replace — preserve UA + Referer.
            params["http_headers"]["Cookie"] = f"SESSDATA={sessdata}"
        try:
            info = await asyncio.to_thread(self._extract, params, url, True)
        except SourceUnavailable:
            target.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            raise SourceUnavailable(f"yt-dlp/bilibili failed: {exc}") from exc
        if not target.is_file():
            raise SourceUnavailable(
                "yt-dlp/bilibili did not produce expected output"
            )
        info_dict = info or {}
        raw_duration = info_dict.get("duration")
        return AudioMetadata(
            source=self.source,
            canonical_url=str(info_dict.get("webpage_url") or url),
            title=str(info_dict.get("title") or target.stem),
            duration_seconds=int(raw_duration) if raw_duration else None,
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )

    def _extract(
        self,
        params: dict[str, Any],
        query: str,
        download: bool,
    ) -> dict[str, Any] | None:
        try:
            with self._factory(params) as ydl:
                return ydl.extract_info(query, download=download)
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(str(exc)) from exc
