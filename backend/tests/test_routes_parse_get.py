"""Tests for GET /api/parse/{token} — fetch a previously-saved parse record."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from utils.cache import cache_path_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def test_get_parse_record_returns_full_payload():
    fake_url = "https://example.com/parse-get-twinkle.mid"
    target = cache_path_for_url(fake_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, target)

    client = TestClient(app)
    parse_resp = client.post(
        "/api/parse",
        json={
            "result_id": "x",
            "download_url": fake_url,
            "title": "Twinkle",
        },
    )
    assert parse_resp.status_code == 200
    token = parse_resp.json()["file_token"]

    fetch_resp = client.get(f"/api/parse/{token}")
    assert fetch_resp.status_code == 200
    body = fetch_resp.json()
    assert body["file_token"] == token
    assert body["title"] == "Twinkle"
    assert body["bpm"] == 120
    assert len(body["tracks"]) == 3


def test_get_parse_record_unknown_returns_404():
    client = TestClient(app)
    resp = client.get("/api/parse/tmp_nope")
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"
