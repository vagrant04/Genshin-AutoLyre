"""Tests for BilibiliSource.

Search now goes through Bilibili's official web search API (httpx),
not yt-dlp's `bilisearch:` prefix — the latter mixes plain videos with
Cheese (paid course) URLs that the BiliBili extractor can't handle.
Download still uses yt-dlp; we mock both layers.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.bilibili import BilibiliSource
from config import AudioSourceKey


# ---- yt-dlp stub (download path) ----

_VIDEO_INFO = {
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
        if q == "https://www.bilibili.com/video/BV1xx":
            if download:
                Path(self.params["outtmpl"]).write_bytes(b"BILI_AUDIO")
            return _VIDEO_INFO
        raise RuntimeError(f"unexpected: {q}")


def _ydl_factory(params): return _StubYDL(params)


# ---- httpx mock (search path) ----

_SEARCH_RESPONSE = {
    "code": 0,
    "data": {
        "result": [
            {
                "result_type": "video",
                "data": [
                    {
                        "bvid": "BV1xx",
                        "title": "<em class=\"keyword\">晴天</em> piano cover",
                        "author": "Up主",
                        "duration": "4:10",
                        "pic": "//i0.hdslb.com/cover.jpg",
                    },
                    {
                        # Search results sometimes contain Cheese (paid
                        # course) entries with no bvid — we must skip them.
                        "bvid": "",
                        "title": "Cheese course",
                        "duration": "10:00",
                    },
                ],
            }
        ],
    },
}


def _httpx_mock(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        assert "search/all" in str(request.url)
        return httpx.Response(200, json=payload)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_search_returns_candidates():
    async with _httpx_mock(_SEARCH_RESPONSE) as client:
        src = BilibiliSource(ydl_factory=_ydl_factory, http_client=client)
        out = await src.search("晴天", limit=3)
    # Cheese entry with empty bvid is skipped; one BV-id candidate left.
    assert len(out) == 1
    assert out[0].source == AudioSourceKey.BILIBILI
    assert out[0].candidate_id == "BV1xx"
    assert out[0].canonical_url == "https://www.bilibili.com/video/BV1xx"
    # <em> stripped from title.
    assert "<em" not in out[0].title and out[0].title.startswith("晴天 piano")
    # 4:10 → 250 seconds.
    assert out[0].duration_seconds == 250
    # Protocol-relative thumbnail prefixed with https.
    assert out[0].thumbnail_url.startswith("https://")


async def test_search_skips_non_video_sections():
    payload = {
        "code": 0,
        "data": {
            "result": [
                {"result_type": "bili_user", "data": [{"name": "Up"}]},
                {
                    "result_type": "video",
                    "data": [{"bvid": "BV2yy", "title": "real", "duration": "3:30"}],
                },
            ],
        },
    }
    async with _httpx_mock(payload) as client:
        src = BilibiliSource(ydl_factory=_ydl_factory, http_client=client)
        out = await src.search("x", limit=5)
    assert len(out) == 1
    assert out[0].candidate_id == "BV2yy"


async def test_search_swallows_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream broken")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        src = BilibiliSource(ydl_factory=_ydl_factory, http_client=client)
        out = await src.search("x", limit=5)
    # AbstractAudioSource.search() swallows exceptions → empty list.
    assert out == []


async def test_fetch_writes_audio(tmp_path: Path):
    src = BilibiliSource(ydl_factory=_ydl_factory)
    out = tmp_path / "x.m4a"
    meta = await src.fetch_to_path(
        "https://www.bilibili.com/video/BV1xx", out
    )
    assert out.is_file()
    assert meta.source == AudioSourceKey.BILIBILI
    assert meta.duration_seconds == 250
