"""Tests for QQMusicSource. qqmusic-api-python calls are replaced with stubs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.qqmusic import QQMusicSource
from config import AudioSourceKey


class _StubClient:
    def __init__(self, search_result, audio_url, payload=b"QQ_AUDIO"):
        self._search = search_result
        self._audio_url = audio_url
        self._payload = payload

    def search(self, keyword, limit): return self._search
    def get_audio_url(self, song_mid): return self._audio_url
    async def download(self, url, target: Path):
        target.write_bytes(self._payload)


_SEARCH_OK = {
    "data": {
        "song": {
            "list": [
                {
                    "songmid": "abc123",
                    "songname": "晴天",
                    "singer": [{"name": "周杰伦"}],
                    "interval": 250,
                    "albumname": "叶惠美",
                }
            ]
        }
    }
}


async def test_search_returns_candidates():
    src = QQMusicSource(client=_StubClient(_SEARCH_OK, audio_url=None))
    out = await src.search("晴天", limit=5)
    assert len(out) == 1
    assert out[0].source == AudioSourceKey.QQMUSIC
    assert out[0].candidate_id == "abc123"
    assert out[0].duration_seconds == 250


async def test_fetch_raises_when_paywalled(tmp_path: Path):
    src = QQMusicSource(client=_StubClient(_SEARCH_OK, audio_url=None))
    with pytest.raises(SourceUnavailable):
        await src.fetch_to_path(
            "https://y.qq.com/n/ryqq/songDetail/abc123", tmp_path / "x.m4a"
        )


async def test_fetch_writes_audio(tmp_path: Path):
    src = QQMusicSource(
        client=_StubClient(
            _SEARCH_OK,
            audio_url="https://dl.stream.qqmusic.qq.com/whatever.m4a",
        )
    )
    target = tmp_path / "x.m4a"
    meta = await src.fetch_to_path(
        "https://y.qq.com/n/ryqq/songDetail/abc123", target
    )
    assert target.is_file()
    assert meta.source == AudioSourceKey.QQMUSIC
