"""Tests for YouTubeSource. yt-dlp's extract_info is replaced by a
pure-python stub (no network)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.youtube import YouTubeSource
from config import AudioSourceKey


_VIDEO_1 = {
    "id": "abc123",
    "title": "Twinkle piano cover",
    "uploader": "Anon",
    "duration": 180,
    "thumbnail": "https://yt/abc123.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
}
_VIDEO_2 = {
    "id": "def456",
    "title": "Another song",
    "uploader": "Anon2",
    "duration": 240,
    "thumbnail": "https://yt/def456.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=def456",
}


class _StubYDL:
    """Drop-in for yt_dlp.YoutubeDL within a `with` block."""

    def __init__(self, params: dict[str, Any]):
        self.params = params
        self.calls: list[tuple[str, bool]] = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, query: str, download: bool):
        self.calls.append((query, download))
        if query.startswith("ytsearch"):
            return {"entries": [_VIDEO_1, _VIDEO_2]}
        if query == "https://www.youtube.com/watch?v=abc123":
            if download:
                Path(self.params["outtmpl"]).write_bytes(b"FAKE_MP3")
            return _VIDEO_1
        raise RuntimeError(f"unexpected query: {query}")


def _factory(params): return _StubYDL(params)


async def test_search_returns_candidates():
    src = YouTubeSource(ydl_factory=_factory)
    out = await src.search("twinkle", limit=5)
    assert len(out) == 2
    assert out[0].source == AudioSourceKey.YOUTUBE
    assert out[0].candidate_id == "abc123"
    assert "Twinkle" in out[0].title
    assert out[0].duration_seconds == 180
    assert out[0].canonical_url.endswith("v=abc123")


async def test_fetch_writes_audio(tmp_path: Path):
    src = YouTubeSource(ydl_factory=_factory)
    target = tmp_path / "yt_abc123.mp3"
    meta = await src.fetch_to_path(
        "https://www.youtube.com/watch?v=abc123", target
    )
    assert target.is_file()
    assert meta.title == "Twinkle piano cover"
    assert meta.source == AudioSourceKey.YOUTUBE
    assert meta.file_size_bytes > 0


async def test_fetch_propagates_extractor_failure_as_unavailable(tmp_path: Path):
    class _FailingYDL:
        def __init__(self, params): self.params = params
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, q, download):
            raise RuntimeError("yt-dlp blew up")

    src = YouTubeSource(ydl_factory=lambda p: _FailingYDL(p))
    with pytest.raises(SourceUnavailable):
        await src.fetch_to_path(
            "https://www.youtube.com/watch?v=abc123", tmp_path / "x.mp3"
        )
