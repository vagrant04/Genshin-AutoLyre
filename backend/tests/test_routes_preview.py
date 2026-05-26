"""Tests for /api/preview-track."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from utils.cache import cache_path_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def _seed_token() -> str:
    fake_url = "https://example.com/twinkle-preview.mid"
    target = cache_path_for_url(fake_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, target)
    client = TestClient(app)
    resp = client.post(
        "/api/parse",
        json={"result_id": "x", "download_url": fake_url, "title": "Twinkle"},
    )
    return resp.json()["file_token"]


def test_preview_returns_mapped_notes():
    from mapper.constants import LEGAL_MIDI_SET

    token = _seed_token()
    client = TestClient(app)
    resp = client.get(
        "/api/preview-track",
        params={"file_token": token, "track_index": 0, "mapped": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapped"] is True
    assert body["track_index"] == 0
    assert body["bpm"] == 120
    assert len(body["notes"]) > 0
    # Every mapped note must be a legal lyre MIDI number.
    for note in body["notes"]:
        assert note["midi"] in LEGAL_MIDI_SET
        assert note["start_ms"] >= 0
        assert note["duration_ms"] > 0


def test_preview_returns_raw_notes():
    token = _seed_token()
    client = TestClient(app)
    resp = client.get(
        "/api/preview-track",
        params={"file_token": token, "track_index": 2, "mapped": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapped"] is False
    # Track 2 in the fixture is the bass: pitches 36, 41, 43 — below C3.
    midi_values = {n["midi"] for n in body["notes"]}
    assert midi_values == {36, 41, 43}


def test_preview_unknown_token_returns_404():
    client = TestClient(app)
    resp = client.get(
        "/api/preview-track",
        params={"file_token": "tmp_unknown", "track_index": 0, "mapped": True},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"


def test_preview_invalid_track_returns_400():
    token = _seed_token()
    client = TestClient(app)
    resp = client.get(
        "/api/preview-track",
        params={"file_token": token, "track_index": 99, "mapped": True},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_TRACK_INDEX"


def test_preview_includes_track_metadata():
    token = _seed_token()
    client = TestClient(app)
    resp = client.get(
        "/api/preview-track",
        params={"file_token": token, "track_index": 0, "mapped": True},
    )
    body = resp.json()
    assert body["track_name"]
    assert body["ticks_per_beat"] == 480
    assert body["duration_ms"] > 0
