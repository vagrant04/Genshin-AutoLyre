"""Tests for AbstractAudioSource shared behavior."""
from __future__ import annotations

from pathlib import Path

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey


class _FakeRaisingSource(AbstractAudioSource):
    source = AudioSourceKey.YOUTUBE

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        raise RuntimeError("simulated")

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        raise SourceUnavailable("simulated")


class _FakeOkSource(AbstractAudioSource):
    source = AudioSourceKey.BILIBILI

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        return [
            AudioCandidate(
                source=self.source,
                candidate_id="x",
                title="hit",
                canonical_url="https://example.com/x",
            )
        ]

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.write_bytes(b"fake audio")
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title="hit",
            file_path=str(target),
            file_size_bytes=len(b"fake audio"),
        )


async def test_search_swallows_exceptions_returns_empty():
    s = _FakeRaisingSource()
    assert await s.search("foo", limit=5) == []


async def test_search_returns_results_on_success():
    s = _FakeOkSource()
    out = await s.search("foo", limit=5)
    assert len(out) == 1
    assert out[0].title == "hit"
    assert out[0].source == AudioSourceKey.BILIBILI


async def test_fetch_writes_to_target(tmp_path: Path):
    s = _FakeOkSource()
    target = tmp_path / "out.mp3"
    meta = await s.fetch_to_path("https://example.com/x", target)
    assert target.is_file()
    assert meta.file_size_bytes == len(b"fake audio")
    assert meta.title == "hit"
