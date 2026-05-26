"""Tests for /api/generate."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from main import app, file_store
from utils.cache import cache_path_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def _seed_token() -> str:
    """Parse the fixture through /api/parse to get a valid token."""
    fake_url = "https://example.com/twinkle-gen.mid"
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
    return resp.json()["file_token"]


def test_generate_returns_three_versions():
    token = _seed_token()
    client = TestClient(app)
    resp = client.post(
        "/api/generate",
        json={
            "file_token": token,
            "title": "Twinkle",
            "track_roles": {"0": "melody", "1": "accompaniment", "2": "ignored"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    versions = body["versions"]
    assert [v["version"] for v in versions] == ["melody_only", "simplified", "full"]

    # Each version must have label, scores, and stats fields populated.
    for v in versions:
        assert v["version_label"]
        assert isinstance(v["pc_score"], str)
        assert isinstance(v["mobile_score"], str)
        assert v["statistics"]["total_notes"] >= 0


def test_generate_simplified_respects_simultaneous_limit():
    token = _seed_token()
    client = TestClient(app)
    resp = client.post(
        "/api/generate",
        json={
            "file_token": token,
            "title": "Twinkle",
            "track_roles": {"0": "melody", "1": "accompaniment", "2": "ignored"},
        },
    )
    body = resp.json()
    simplified = next(v for v in body["versions"] if v["version"] == "simplified")
    assert simplified["statistics"]["max_simultaneous_keys"] <= 4


def test_generate_no_melody_returns_400():
    token = _seed_token()
    client = TestClient(app)
    resp = client.post(
        "/api/generate",
        json={
            "file_token": token,
            "title": "Twinkle",
            "track_roles": {"0": "ignored", "1": "ignored", "2": "ignored"},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "NO_MELODY_TRACK"


def test_generate_unknown_token_returns_404():
    client = TestClient(app)
    resp = client.post(
        "/api/generate",
        json={
            "file_token": "tmp_unknown",
            "title": "x",
            "track_roles": {"0": "melody"},
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"


def test_generate_invalid_track_index_returns_400():
    token = _seed_token()
    client = TestClient(app)
    resp = client.post(
        "/api/generate",
        json={
            "file_token": token,
            "title": "x",
            "track_roles": {"99": "melody"},
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_TRACK_INDEX"
