"""Tests for /api/parse and /api/upload."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app, file_store
from utils.cache import cache_path_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def test_parse_uses_cached_file_and_returns_tracks(tmp_path: Path, monkeypatch):
    # Pre-cache a file at the URL hash; downloader should be skipped.
    fake_url = "https://example.com/twinkle.mid"
    target = cache_path_for_url(fake_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, target)

    client = TestClient(app)
    resp = client.post(
        "/api/parse",
        json={
            "result_id": "freemidi_x",
            "download_url": fake_url,
            "title": "Twinkle",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Twinkle"
    assert body["bpm"] == 120
    assert body["ticks_per_beat"] == 480
    assert len(body["tracks"]) == 3
    assert all("suggested_role" in t for t in body["tracks"])
    assert body["file_token"].startswith("tmp_")

    # Token must be retrievable from the store.
    record = file_store.get(body["file_token"])
    assert record.title == "Twinkle"


def test_upload_accepts_midi_file():
    with FIXTURE.open("rb") as fh:
        client = TestClient(app)
        resp = client.post(
            "/api/upload",
            files={"file": ("twinkle.mid", fh, "audio/midi")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["bpm"] == 120
    assert body["file_token"].startswith("tmp_")


def test_upload_rejects_non_midi_extension(tmp_path: Path):
    bogus = tmp_path / "x.txt"
    bogus.write_bytes(b"not midi")
    with bogus.open("rb") as fh:
        client = TestClient(app)
        resp = client.post(
            "/api/upload",
            files={"file": ("x.txt", fh, "text/plain")},
        )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_FILE_TYPE"
