"""Tests for BilibiliSource."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.bilibili import BilibiliSource
from config import AudioSourceKey


_VIDEO = {
    "id": "BV1xx",
    "title": "晴天 piano cover",
    "uploader": "Up主",
    "duration": 250,
    "thumbnail": "https://i0.hdslb.com/.../cover.jpg",
    "webpage_url": "https://www.bilibili.com/video/BV1xx",
}


class _StubYDL:
    def __init__(self, params): self.params = params
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def extract_info(self, q, download):
        if q.startswith("bilisearch"):
            return {"entries": [_VIDEO]}
        if q == "https://www.bilibili.com/video/BV1xx":
            if download:
                Path(self.params["outtmpl"]).write_bytes(b"BILI_AUDIO")
            return _VIDEO
        raise RuntimeError(f"unexpected: {q}")


def _factory(params): return _StubYDL(params)


async def test_search_uses_bilisearch_prefix():
    captured = []

    class _Capture(_StubYDL):
        def extract_info(self, q, download):
            captured.append(q)
            return super().extract_info(q, download)

    src = BilibiliSource(ydl_factory=lambda p: _Capture(p))
    await src.search("晴天", limit=3)
    assert captured and captured[0].startswith("bilisearch3:")


async def test_search_returns_candidates():
    src = BilibiliSource(ydl_factory=_factory)
    out = await src.search("晴天", limit=3)
    assert len(out) == 1
    assert out[0].source == AudioSourceKey.BILIBILI
    assert out[0].candidate_id == "BV1xx"
    assert "BV1xx" in out[0].canonical_url


async def test_fetch_writes_audio(tmp_path: Path):
    src = BilibiliSource(ydl_factory=_factory)
    out = tmp_path / "x.m4a"
    meta = await src.fetch_to_path(
        "https://www.bilibili.com/video/BV1xx", out
    )
    assert out.is_file()
    assert meta.source == AudioSourceKey.BILIBILI
