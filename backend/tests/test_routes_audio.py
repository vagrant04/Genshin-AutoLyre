"""Tests for /api/audio/* routes."""
from __future__ import annotations

import time
from pathlib import Path

import mido
import pytest
from fastapi.testclient import TestClient

from audio.store import JobStage
from config import AudioCandidate, AudioMetadata, AudioSourceKey
from main import app


class _StubYouTube:
    source = AudioSourceKey.YOUTUBE

    async def search(self, query, limit=5):
        return [
            AudioCandidate(
                source=self.source,
                candidate_id="abc123",
                title="Twinkle piano cover",
                artist="Anon",
                duration_seconds=120,
                thumbnail_url="https://yt/abc123.jpg",
                canonical_url="https://www.youtube.com/watch?v=abc123",
            )
        ]

    async def fetch_to_path(self, url, target: Path):
        target.write_bytes(b"FAKE_AUDIO")
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title="Twinkle",
            duration_seconds=120,
            file_path=str(target),
            file_size_bytes=10,
        )


def _build_tiny_midi(path: Path) -> None:
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Piano", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    mid.save(str(path))


async def _stub_transcribe(audio_path: Path, midi_out_path: Path, **kwargs):
    _build_tiny_midi(midi_out_path)
    return midi_out_path


@pytest.fixture
def audio_overrides(tmp_path):
    """Wire the app's audio dependencies to test stubs."""
    from api import routes_audio

    app.dependency_overrides[routes_audio.get_source_for_platform] = (
        lambda platform: _StubYouTube()
    )
    app.dependency_overrides[routes_audio.get_source_for_url] = (
        lambda url: _StubYouTube()
    )
    app.dependency_overrides[routes_audio.get_transcribe_fn] = (
        lambda: _stub_transcribe
    )
    app.dependency_overrides[routes_audio.get_audio_cache_root] = (
        lambda: tmp_path
    )
    yield
    app.dependency_overrides.pop(routes_audio.get_source_for_platform, None)
    app.dependency_overrides.pop(routes_audio.get_source_for_url, None)
    app.dependency_overrides.pop(routes_audio.get_transcribe_fn, None)
    app.dependency_overrides.pop(routes_audio.get_audio_cache_root, None)


def test_audio_search_returns_candidates(audio_overrides):
    client = TestClient(app)
    resp = client.get(
        "/api/audio/search",
        params={"q": "twinkle", "platform": "youtube", "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "twinkle"
    assert body["platform"] == "youtube"
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["candidate_id"] == "abc123"


def test_audio_search_invalid_platform_returns_422():
    client = TestClient(app)
    resp = client.get(
        "/api/audio/search",
        params={"q": "twinkle", "platform": "spotify"},
    )
    assert resp.status_code == 422


def _wait_for_done(client: TestClient, job_token: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get(f"/api/audio/jobs/{job_token}")
        body = resp.json()
        if body["stage"] in ("done", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_token} did not finish in {timeout}s")


def test_transcribe_url_completes(audio_overrides):
    client = TestClient(app)
    resp = client.post(
        "/api/audio/transcribe",
        data={
            "input_mode": "url",
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Twinkle",
            "onset_sensitivity": "medium",
            "min_note_ms": "60",
        },
    )
    assert resp.status_code == 200, resp.text
    job_token = resp.json()["job_token"]
    assert job_token.startswith("aud_")

    final = _wait_for_done(client, job_token)
    assert final["stage"] == "done"
    assert final["parse_token"] is not None


def test_transcribe_url_with_invalid_host_returns_400():
    client = TestClient(app)
    resp = client.post(
        "/api/audio/transcribe",
        data={
            "input_mode": "url",
            "url": "https://example.com/not-a-platform",
            "title": "x",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_AUDIO_URL"


def test_transcribe_candidate_completes(audio_overrides):
    client = TestClient(app)
    resp = client.post(
        "/api/audio/transcribe",
        data={
            "input_mode": "candidate",
            "source": "youtube",
            "canonical_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Twinkle",
            "onset_sensitivity": "medium",
            "min_note_ms": "60",
        },
    )
    assert resp.status_code == 200, resp.text
    job_token = resp.json()["job_token"]
    final = _wait_for_done(client, job_token)
    assert final["stage"] == "done"


def test_transcribe_upload_completes(audio_overrides, tmp_path):
    fake_mp3 = tmp_path / "song.mp3"
    fake_mp3.write_bytes(b"PRETEND_MP3")

    client = TestClient(app)
    with fake_mp3.open("rb") as fh:
        resp = client.post(
            "/api/audio/transcribe",
            data={
                "input_mode": "upload",
                "title": "Local Song",
                "onset_sensitivity": "medium",
                "min_note_ms": "60",
            },
            files={"file": ("song.mp3", fh, "audio/mpeg")},
        )
    assert resp.status_code == 200, resp.text
    job_token = resp.json()["job_token"]
    final = _wait_for_done(client, job_token)
    assert final["stage"] == "done"


def test_transcribe_upload_rejects_non_audio_extension():
    client = TestClient(app)
    resp = client.post(
        "/api/audio/transcribe",
        data={
            "input_mode": "upload",
            "title": "x",
            "onset_sensitivity": "medium",
            "min_note_ms": "60",
        },
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_FILE_TYPE"


def test_jobs_unknown_token_returns_404():
    client = TestClient(app)
    resp = client.get("/api/audio/jobs/aud_unknown")
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"
