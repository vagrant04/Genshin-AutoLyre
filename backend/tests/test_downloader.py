"""Tests for utils.downloader. Spec §8.2.1."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from utils.downloader import DownloadError, download_to_path

MIDI_HEADER = b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60"


@pytest.fixture
def make_client():
    def _make(handler):
        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport)
    return _make


async def test_downloads_file_to_path(tmp_path: Path, make_client):
    payload = MIDI_HEADER + b"\x00" * 1024

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    target = tmp_path / "out.mid"
    async with make_client(handler) as client:
        await download_to_path("https://example.com/x.mid", target, client=client)
    assert target.read_bytes() == payload


async def test_rejects_files_over_size_limit(tmp_path: Path, make_client):
    huge = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=huge,
            headers={"content-length": str(len(huge))},
        )

    target = tmp_path / "out.mid"
    async with make_client(handler) as client:
        with pytest.raises(DownloadError):
            await download_to_path("https://example.com/big.mid", target, client=client)
    assert not target.exists()


async def test_raises_on_http_error(tmp_path: Path, make_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    target = tmp_path / "out.mid"
    async with make_client(handler) as client:
        with pytest.raises(DownloadError):
            await download_to_path("https://example.com/missing.mid", target, client=client)
    assert not target.exists()


async def test_streams_without_content_length(tmp_path: Path, make_client):
    # Some servers don't send Content-Length; downloader must still cap by bytes read.
    payload = MIDI_HEADER + b"\x00" * 100

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)  # no header set explicitly

    target = tmp_path / "out.mid"
    async with make_client(handler) as client:
        await download_to_path("https://example.com/x.mid", target, client=client)
    assert target.read_bytes() == payload
