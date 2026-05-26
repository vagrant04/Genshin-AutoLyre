# Audio-to-MIDI Pipeline — Plan 2: FastAPI routes

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **DEVIATION (2026-05-23): NetEase dropped.** See Plan 1's deviation header. In this plan, when implementing `routes_audio.py`:
> - The `PlatformParam = Literal[...]` should list THREE values: `"youtube"`, `"bilibili"`, `"qqmusic"`.
> - `_SOURCE_BY_PLATFORM` should map THREE keys, no `"netease"`.
> - `_platform_from_url()` should drop the `music.163.com` branch.
> - Skip the `from audio.sources.netease import NetEaseSource` import.

**Goal:** Wire the audio package (built in plan 1) into HTTP routes — `/api/audio/search`, `/api/audio/transcribe`, and `/api/audio/jobs/{token}` — registered alongside the existing `/api/search`, `/api/parse`, etc. The transcribe pipeline reuses the existing `_parse_and_save()` helper so the response shape is identical to `/api/parse`, and the frontend's downstream flow (TrackConfig → Score) requires no changes.

**Architecture:** A single `routes_audio.py` exposes three endpoints. Search dispatches to one of the three `AudioSource` subclasses by `platform` query param. Transcribe runs synchronously in a background task seeded by an `AudioFileStore` job token — the route returns the job token immediately, the job runs (download → cache check → transcribe → cache check → parse → store update), and the frontend polls `/api/audio/jobs/{token}` for stage progress. New error codes plumb in via the existing `errors.py` catalog.

**Tech Stack:** FastAPI (already installed), the audio package from plan 1, the existing `_parse_and_save()` helper, `BackgroundTasks` from Starlette.

---

## File structure (this plan)

```
backend/
├── api/
│   ├── errors.py                       MODIFY (+5 error codes)
│   ├── routes_audio.py                 NEW (3 routes)
│   └── routes_parse.py                 MODIFY (extract `_parse_and_save` so it's importable cleanly)
├── audio/
│   └── pipeline.py                     NEW (the orchestrator: download → transcribe → parse)
├── main.py                             MODIFY (register router; create cache dirs; expose audio_store)
└── tests/
    ├── test_audio_pipeline.py          NEW (offline orchestrator tests)
    └── test_routes_audio.py            NEW (TestClient + dependency overrides)
```

**Responsibility split:**
- `audio/pipeline.py` is the **only** place that knows the full `download → transcribe → parse → store update` sequence. The route is thin.
- The route file holds request/response Pydantic models, dependency wiring, and the BackgroundTasks scheduling.
- `routes_parse.py` gets a tiny refactor to make `_parse_and_save` a top-level public helper (it's currently a module-private `_parse_and_save`); the existing parse route keeps using it, and the audio pipeline imports it.

---

## Task 1: Add error codes for audio failures

**Files:**
- Modify: `backend/api/errors.py`

- [ ] **Step 1: Append five new entries to `ERROR_CATALOG`**

Open `backend/api/errors.py` and add five entries inside the existing `ERROR_CATALOG` dict (after the last existing entry):

```python
    "AUDIO_DOWNLOAD_FAILED": (status.HTTP_400_BAD_REQUEST, "音频下载失败。"),
    "AUDIO_TOO_LARGE": (status.HTTP_400_BAD_REQUEST, "音频文件超过 50MB 限制。"),
    "AUDIO_TOO_LONG": (status.HTTP_400_BAD_REQUEST, "音频时长超过 10 分钟限制。"),
    "TRANSCRIPTION_FAILED": (status.HTTP_500_INTERNAL_SERVER_ERROR, "音频转 MIDI 失败。"),
    "SOURCE_UNAVAILABLE": (status.HTTP_503_SERVICE_UNAVAILABLE, "该平台接口当前不可用或歌曲需要付费，请换个歌曲或平台重试。"),
    "INVALID_AUDIO_URL": (status.HTTP_400_BAD_REQUEST, "无法识别的音频 URL。"),
```

- [ ] **Step 2: Verify import**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "from api.errors import make_error; e = make_error('AUDIO_TOO_LARGE'); print(e.code, e.http_status)"`
Expected: `AUDIO_TOO_LARGE 400`.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/api/errors.py && git commit -m "feat(api): error codes for audio + transcription failures"
```

---

## Task 2: Make `_parse_and_save` importable

**Files:**
- Modify: `backend/api/routes_parse.py`

The audio pipeline needs to feed a transcribed MIDI through the same `parse_midi_file → classify_tracks → store.save` flow that `/api/parse` uses. Currently `_parse_and_save` is a module-private function inside `routes_parse.py`. Rather than duplicating the logic, expose it.

- [ ] **Step 1: Rename `_parse_and_save` → `parse_and_save_midi` in `routes_parse.py`**

In `backend/api/routes_parse.py`, find every occurrence of the symbol `_parse_and_save` and replace it with `parse_and_save_midi`. There are exactly three call sites (in `parse()`, in `upload()`, and the function definition itself).

Edit the function definition:

```python
def parse_and_save_midi(path: Path, title: str, store: ParsedFileStore) -> dict:
```

Edit `parse()`:

```python
    return parse_and_save_midi(target, payload.title, store)
```

Edit `upload()`:

```python
    return parse_and_save_midi(target, title, store)
```

- [ ] **Step 2: Verify the existing parse tests still pass**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_routes_parse.py -v 2>&1 | tail -5`
Expected: all parse tests still PASS — this is a pure rename, no behavior change.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/api/routes_parse.py && git commit -m "refactor(api): expose parse_and_save_midi for cross-route reuse"
```

---

## Task 3: Pipeline orchestrator — failing tests

**Files:**
- Create: `backend/tests/test_audio_pipeline.py`

The orchestrator wraps the full download → cache → transcribe → cache → parse sequence. We test it in isolation by injecting stub source + stub transcriber.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for audio.pipeline.run_transcribe_pipeline.

The orchestrator is exercised offline via dependency injection:
- A fake AudioSource writes a known byte string to the target path.
- A fake transcriber writes a small MIDI to the target path (using mido).
- A real ParsedFileStore captures the parse output.

We verify the full sequence: cache miss → download → transcribe →
parse → store update; cache hit short-circuits.
"""
from __future__ import annotations

from pathlib import Path

import mido
import pytest

from audio.exceptions import SourceUnavailable, TranscriptionError
from audio.pipeline import run_transcribe_pipeline, TranscribeRequest
from audio.store import AudioFileStore, JobStage
from api.store import ParsedFileStore
from config import AudioMetadata, AudioSourceKey


# ---------- helpers ----------

def _build_tiny_midi(path: Path) -> None:
    """Write a 1-track, 1-note MIDI to `path`."""
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Piano", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    mid.save(str(path))


class _StubSource:
    source = AudioSourceKey.YOUTUBE

    def __init__(self, payload: bytes = b"FAKE_AUDIO"):
        self._payload = payload
        self.fetch_calls = 0

    async def search(self, query, limit=5): return []

    async def fetch_to_path(self, url: str, target: Path):
        self.fetch_calls += 1
        target.write_bytes(self._payload)
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title="stub song",
            duration_seconds=120,
            file_path=str(target),
            file_size_bytes=len(self._payload),
        )


async def _stub_transcribe(audio_path: Path, midi_out_path: Path, **kwargs):
    """Drop a tiny MIDI into the requested output path."""
    _build_tiny_midi(midi_out_path)
    return midi_out_path


# ---------- tests ----------

async def test_pipeline_completes_full_sequence(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://www.youtube.com/watch?v=abc",
        title="Twinkle",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    await run_transcribe_pipeline(
        job_token=job_token,
        request=req,
        source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store,
        audio_store=audio_store,
        cache_root=tmp_path,
    )

    job = audio_store.get(job_token)
    assert job.stage == JobStage.DONE
    assert job.parse_token is not None
    assert job.parse_token.startswith("tmp_")
    # Parse store must contain a record with the title.
    record = parse_store.get(job.parse_token)
    assert record.title == "Twinkle"


async def test_pipeline_uses_cached_audio_on_repeat(tmp_path: Path):
    """Second invocation with the same URL skips the download."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://example.com/x",
        title="x",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    # First run.
    t1 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t1, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    # Second run.
    t2 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t2, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert src.fetch_calls == 1   # second run hit the cache


async def test_pipeline_uses_cached_midi_on_repeat(tmp_path: Path):
    """Same URL + same params → MIDI cache hit, transcriber not called twice."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://example.com/y",
        title="y",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    transcribe_calls = 0

    async def _counting(audio_path, midi_out_path, **kwargs):
        nonlocal transcribe_calls
        transcribe_calls += 1
        _build_tiny_midi(midi_out_path)
        return midi_out_path

    t1 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t1, request=req, source=src,
        transcribe_fn=_counting,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    t2 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t2, request=req, source=src,
        transcribe_fn=_counting,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert transcribe_calls == 1


async def test_pipeline_marks_error_on_source_failure(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    class _Failing:
        source = AudioSourceKey.NETEASE
        async def search(self, q, limit=5): return []
        async def fetch_to_path(self, url, target):
            raise SourceUnavailable("paywalled")

    req = TranscribeRequest(
        canonical_url="https://music.163.com/song?id=999",
        title="paywall",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=_Failing(),
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    job = audio_store.get(job_token)
    assert job.stage == JobStage.ERROR
    assert "paywalled" in (job.error or "")


async def test_pipeline_marks_error_on_transcription_failure(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()
    src = _StubSource()

    async def _bad_transcribe(audio_path, midi_out_path, **kwargs):
        raise TranscriptionError("model crashed")

    req = TranscribeRequest(
        canonical_url="https://example.com/crash",
        title="x",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=src,
        transcribe_fn=_bad_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    job = audio_store.get(job_token)
    assert job.stage == JobStage.ERROR
    assert "model crashed" in (job.error or "")


async def test_pipeline_uses_local_upload_path(tmp_path: Path):
    """When `local_audio_path` is set, source.fetch_to_path is never called."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    # Simulate an already-uploaded audio file.
    local_audio = tmp_path / "uploaded.mp3"
    local_audio.write_bytes(b"UPLOADED_AUDIO")

    src = _StubSource()  # should NOT be called.
    req = TranscribeRequest(
        canonical_url=None,
        title="uploaded.mp3",
        onset_threshold=0.5,
        min_note_length_ms=60,
        local_audio_path=local_audio,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert src.fetch_calls == 0
    assert audio_store.get(job_token).stage == JobStage.DONE
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_pipeline.py -v 2>&1 | tail -5`
Expected: import error (`audio.pipeline` does not exist).

- [ ] **Step 3: Commit RED**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/tests/test_audio_pipeline.py && git commit -m "test(audio): pipeline orchestrator spec tests (RED)"
```

---

## Task 4: Pipeline orchestrator implementation

**Files:**
- Create: `backend/audio/pipeline.py`

- [ ] **Step 1: Write the orchestrator**

```python
"""Audio → MIDI → parsed-MIDI pipeline orchestrator.

Single entry point: `run_transcribe_pipeline()`. Inputs are an audio
source, a transcribe function (so tests can substitute the real Basic
Pitch call), the two stores, and a request object. Side effects:
  - Updates audio_store as the job progresses.
  - Caches the downloaded audio under cache_root/audio/.
  - Caches the transcribed MIDI under cache_root/midi/transcribed/.
  - Inserts the parsed MIDI into parse_store.
  - On any failure, marks the job ERROR with a human-readable message.

`source` follows the `AbstractAudioSource` interface from plan 1, but
is typed loosely so tests can use minimal stubs.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, Protocol

from audio.exceptions import (
    AudioError,
    SourceUnavailable,
    TranscriptionError,
)
from audio.store import AudioFileStore, JobStage
from api.routes_parse import parse_and_save_midi
from api.store import ParsedFileStore

_LOG = logging.getLogger(__name__)


@dataclass
class TranscribeRequest:
    """Inputs needed by the orchestrator.

    Either `canonical_url` (for source-fetched audio) or
    `local_audio_path` (for uploaded audio) must be set.
    """
    title: str
    onset_threshold: float
    min_note_length_ms: int
    canonical_url: Optional[str] = None
    local_audio_path: Optional[Path] = None


class _SourceLike(Protocol):
    async def fetch_to_path(self, url: str, target: Path) -> Any: ...


# Type for the injected transcribe function. Production code uses
# `audio.transcriber.transcribe`. Tests inject a stub that writes a
# tiny MIDI without invoking Basic Pitch.
TranscribeFn = Callable[..., Awaitable[Path]]


async def run_transcribe_pipeline(
    *,
    job_token: str,
    request: TranscribeRequest,
    source: _SourceLike,
    transcribe_fn: TranscribeFn,
    parse_store: ParsedFileStore,
    audio_store: AudioFileStore,
    cache_root: Path,
) -> None:
    audio_dir = cache_root / "audio"
    midi_dir = cache_root / "midi" / "transcribed"
    audio_dir.mkdir(parents=True, exist_ok=True)
    midi_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ---- Stage 1: obtain audio ----
        audio_path = await _resolve_audio(
            request=request,
            source=source,
            audio_dir=audio_dir,
            audio_store=audio_store,
            job_token=job_token,
        )

        # ---- Stage 2: transcribe (with cache) ----
        audio_store.update(job_token, stage=JobStage.TRANSCRIBING)
        midi_path = _midi_cache_path(
            request=request,
            audio_path=audio_path,
            midi_dir=midi_dir,
        )
        if not midi_path.is_file():
            await transcribe_fn(
                audio_path,
                midi_path,
                onset_threshold=request.onset_threshold,
                min_note_length_ms=request.min_note_length_ms,
            )

        # ---- Stage 3: parse + save ----
        audio_store.update(job_token, stage=JobStage.PARSING)
        parsed = parse_and_save_midi(midi_path, request.title, parse_store)
        audio_store.update(
            job_token,
            stage=JobStage.DONE,
            parse_token=parsed["file_token"],
        )
    except SourceUnavailable as exc:
        _LOG.warning("audio job %s SOURCE_UNAVAILABLE: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except TranscriptionError as exc:
        _LOG.warning("audio job %s TRANSCRIPTION_FAILED: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except AudioError as exc:
        _LOG.warning("audio job %s AUDIO_ERROR: %s", job_token, exc)
        audio_store.update(job_token, stage=JobStage.ERROR, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — final safety net
        _LOG.exception("audio job %s unexpected failure", job_token)
        audio_store.update(
            job_token, stage=JobStage.ERROR, error=f"unexpected: {exc}"
        )


async def _resolve_audio(
    *,
    request: TranscribeRequest,
    source: _SourceLike,
    audio_dir: Path,
    audio_store: AudioFileStore,
    job_token: str,
) -> Path:
    """Either return the user-uploaded audio path, or download from the source."""
    if request.local_audio_path is not None:
        # Trust the caller; route layer already validated existence.
        return request.local_audio_path

    if not request.canonical_url:
        raise AudioError("transcribe request has neither url nor local audio")

    audio_path = _audio_cache_path(request.canonical_url, audio_dir)
    if audio_path.is_file():
        return audio_path

    audio_store.update(job_token, stage=JobStage.DOWNLOADING)
    await source.fetch_to_path(request.canonical_url, audio_path)
    return audio_path


def _audio_cache_path(canonical_url: str, audio_dir: Path) -> Path:
    h = hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()[:16]
    # We don't know the suffix yet; the source writes whichever container
    # it produces. Use .audio as a generic extension.
    return audio_dir / f"{h}.audio"


def _midi_cache_path(
    *,
    request: TranscribeRequest,
    audio_path: Path,
    midi_dir: Path,
) -> Path:
    """Cache key includes the URL/local path AND the transcription params,
    so re-running with different params correctly bypasses the cache."""
    seed = f"{request.canonical_url or audio_path}::"
    seed += f"{request.onset_threshold}::{request.min_note_length_ms}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return midi_dir / f"{h}.mid"
```

- [ ] **Step 2: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_pipeline.py -v 2>&1 | tail -10`
Expected: all 6 pipeline tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/pipeline.py && git commit -m "feat(audio): pipeline orchestrator with cache + job tracking"
```

---

## Task 5: Routes — failing tests

**Files:**
- Create: `backend/tests/test_routes_audio.py`

The route tests use FastAPI's `TestClient` with dependency overrides to substitute fake sources, fake transcribers, and a clean `AudioFileStore` per test. We avoid the network entirely.

- [ ] **Step 1: Write failing tests**

```python
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


# ---- helpers ----

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
def audio_overrides(tmp_path, monkeypatch):
    """Wire the app's audio dependencies to test stubs.

    Returns a tuple (cleanup_fn) so the caller can restore.
    The audio routes use FastAPI Depends() for: get_source, get_transcribe_fn,
    get_audio_cache_root. We override those.
    """
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


# ---- /api/audio/search ----

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


# ---- /api/audio/transcribe ----

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
        json={
            "input_mode": "url",
            "url": "https://www.youtube.com/watch?v=abc123",
            "title": "Twinkle",
            "onset_sensitivity": "medium",
            "min_note_ms": 60,
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
        json={
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
        json={
            "input_mode": "candidate",
            "source": "youtube",
            "canonical_url": "https://www.youtube.com/watch?v=abc123",
            "title": "Twinkle",
            "onset_sensitivity": "medium",
            "min_note_ms": 60,
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


# ---- /api/audio/jobs/{token} ----

def test_jobs_unknown_token_returns_404():
    client = TestClient(app)
    resp = client.get("/api/audio/jobs/aud_unknown")
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_routes_audio.py -v 2>&1 | tail -5`
Expected: import error or attribute error from `routes_audio` not existing.

- [ ] **Step 3: Commit RED**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/tests/test_routes_audio.py && git commit -m "test(api): /api/audio/* route spec tests (RED)"
```

---

## Task 6: Routes implementation

**Files:**
- Create: `backend/api/routes_audio.py`

The route file holds Pydantic request/response models, FastAPI dependencies (overridable from tests), the three handlers, and platform/URL → source resolution.

- [ ] **Step 1: Write the routes**

```python
"""GET /api/audio/search, POST /api/audio/transcribe, GET /api/audio/jobs/{token}.

Spec: docs/superpowers/specs/2026-05-22-audio-to-midi-design.md.

The transcribe route returns immediately with a job token; the actual
work runs as a FastAPI BackgroundTask. The frontend polls
/api/audio/jobs/{token} until stage = "done" or "error".
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import urlparse

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
)
from pydantic import BaseModel

from api.errors import make_error
from api.routes_parse import get_store as get_parse_store
from api.store import ParsedFileStore
from audio.exceptions import InvalidAudioUrlError
from audio.pipeline import TranscribeRequest, run_transcribe_pipeline
from audio.sources.base import AbstractAudioSource
from audio.sources.bilibili import BilibiliSource
from audio.sources.netease import NetEaseSource
from audio.sources.qqmusic import QQMusicSource
from audio.sources.youtube import YouTubeSource
from audio.store import AudioFileStore, JobStage
from audio.transcriber import (
    DEFAULT_MIN_NOTE_LENGTH_MS,
    SENSITIVITY_PRESETS,
    transcribe as default_transcribe,
)
from config import AudioSourceKey

router = APIRouter(prefix="/api/audio", tags=["audio"])
_LOG = logging.getLogger(__name__)


# ---------- request / response models ----------

PlatformParam = Literal["youtube", "bilibili", "netease", "qqmusic"]
SensitivityParam = Literal["low", "medium", "high"]


class TranscribeUrlRequest(BaseModel):
    input_mode: Literal["url"]
    url: str
    title: Optional[str] = None
    onset_sensitivity: SensitivityParam = "medium"
    min_note_ms: int = DEFAULT_MIN_NOTE_LENGTH_MS


class TranscribeCandidateRequest(BaseModel):
    input_mode: Literal["candidate"]
    source: PlatformParam
    canonical_url: str
    title: str
    onset_sensitivity: SensitivityParam = "medium"
    min_note_ms: int = DEFAULT_MIN_NOTE_LENGTH_MS


# Upload mode uses multipart/form-data; FastAPI gives us each form field
# directly, no Pydantic model required.


class JobStatusResponse(BaseModel):
    job_token: str
    stage: JobStage
    error: Optional[str] = None
    parse_token: Optional[str] = None


# ---------- dependencies (override-friendly for tests) ----------

def get_audio_cache_root() -> Path:
    """Production location for cached audio + transcribed MIDI."""
    return Path("/tmp/genshin_lyre")


def get_audio_store() -> AudioFileStore:
    raise RuntimeError("get_audio_store must be overridden by main.py")


def get_transcribe_fn():
    return default_transcribe


def get_source_for_platform(platform: PlatformParam) -> AbstractAudioSource:
    return _SOURCE_BY_PLATFORM[platform]()


def get_source_for_url(url: str) -> AbstractAudioSource:
    platform = _platform_from_url(url)
    if platform is None:
        raise make_error("INVALID_AUDIO_URL", detail=url)
    return _SOURCE_BY_PLATFORM[platform]()


_SOURCE_BY_PLATFORM: dict[str, type[AbstractAudioSource]] = {
    "youtube": YouTubeSource,
    "bilibili": BilibiliSource,
    "netease": NetEaseSource,
    "qqmusic": QQMusicSource,
}


def _platform_from_url(url: str) -> Optional[PlatformParam]:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return None
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "bilibili.com" in host:
        return "bilibili"
    if "music.163.com" in host:
        return "netease"
    if "qq.com" in host:
        return "qqmusic"
    return None


# ---------- /api/audio/search ----------

@router.get("/search")
async def audio_search(
    q: Annotated[str, Query(min_length=1)],
    platform: Annotated[PlatformParam, Query()],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    source: AbstractAudioSource = Depends(get_source_for_platform),
) -> dict:
    candidates = await source.search(q, limit=limit)
    return {
        "query": q,
        "platform": platform,
        "total": len(candidates),
        "candidates": [c.model_dump(mode="json") for c in candidates],
    }


# ---------- /api/audio/transcribe ----------

@router.post("/transcribe")
async def audio_transcribe(
    background_tasks: BackgroundTasks,
    # All three modes share these inputs; FastAPI treats unsupplied fields as None.
    input_mode: Annotated[Literal["url", "upload", "candidate"], Form()] = "url",
    file: Annotated[Optional[UploadFile], File()] = None,
    url: Annotated[Optional[str], Form()] = None,
    canonical_url: Annotated[Optional[str], Form()] = None,
    source_param: Annotated[Optional[PlatformParam], Form(alias="source")] = None,
    title: Annotated[Optional[str], Form()] = None,
    onset_sensitivity: Annotated[SensitivityParam, Form()] = "medium",
    min_note_ms: Annotated[int, Form(ge=10, le=2000)] = DEFAULT_MIN_NOTE_LENGTH_MS,
    parse_store: ParsedFileStore = Depends(get_parse_store),
    audio_store: AudioFileStore = Depends(get_audio_store),
    transcribe_fn = Depends(get_transcribe_fn),
    cache_root: Path = Depends(get_audio_cache_root),
) -> dict:
    # ---- For JSON requests, FastAPI fills the Form() params from the JSON body. ----
    # Resolve source + audio location based on input_mode.
    source: Optional[AbstractAudioSource] = None
    local_audio_path: Optional[Path] = None
    canonical: Optional[str] = None
    resolved_title: str = title or "Untitled"

    if input_mode == "url":
        if not url:
            raise make_error("INVALID_AUDIO_URL", detail="missing url")
        platform = _platform_from_url(url)
        if platform is None:
            raise make_error("INVALID_AUDIO_URL", detail=url)
        source = _SOURCE_BY_PLATFORM[platform]()
        canonical = url
    elif input_mode == "candidate":
        if not (canonical_url and source_param):
            raise make_error(
                "INVALID_AUDIO_URL",
                detail="candidate mode requires source + canonical_url",
            )
        source = _SOURCE_BY_PLATFORM[source_param]()
        canonical = canonical_url
    elif input_mode == "upload":
        if not file:
            raise make_error("INVALID_FILE_TYPE", detail="missing file")
        filename = file.filename or ""
        if not filename.lower().endswith((".mp3", ".m4a", ".mp4", ".wav", ".aac")):
            raise make_error("INVALID_FILE_TYPE")
        cache_root.mkdir(parents=True, exist_ok=True)
        upload_path = cache_root / "audio" / f"upload_{uuid.uuid4().hex}.audio"
        upload_path.parent.mkdir(parents=True, exist_ok=True)
        contents = await file.read()
        if len(contents) > 50 * 1024 * 1024:
            raise make_error("AUDIO_TOO_LARGE")
        upload_path.write_bytes(contents)
        local_audio_path = upload_path
        resolved_title = title or Path(filename).stem
    else:
        raise make_error("INVALID_AUDIO_URL", detail=f"unknown input_mode: {input_mode}")

    # Map sensitivity preset → onset threshold.
    onset_threshold = SENSITIVITY_PRESETS[onset_sensitivity]

    request = TranscribeRequest(
        title=resolved_title,
        onset_threshold=onset_threshold,
        min_note_length_ms=min_note_ms,
        canonical_url=canonical,
        local_audio_path=local_audio_path,
    )
    job_token = audio_store.create_job()

    # If this is upload mode, we don't need a real source; the orchestrator
    # short-circuits when local_audio_path is set. Pass any source instance.
    if source is None:
        source = YouTubeSource()  # never invoked

    background_tasks.add_task(
        run_transcribe_pipeline,
        job_token=job_token,
        request=request,
        source=source,
        transcribe_fn=transcribe_fn,
        parse_store=parse_store,
        audio_store=audio_store,
        cache_root=cache_root,
    )
    return {"job_token": job_token}


# ---------- /api/audio/jobs/{token} ----------

@router.get("/jobs/{job_token}")
async def audio_job_status(
    job_token: str,
    audio_store: AudioFileStore = Depends(get_audio_store),
) -> dict:
    try:
        job = audio_store.get(job_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND", detail=job_token)
    return JobStatusResponse(
        job_token=job_token,
        stage=job.stage,
        error=job.error,
        parse_token=job.parse_token,
    ).model_dump(mode="json")
```

- [ ] **Step 2: Wire the audio router and store into `main.py`**

Edit `backend/main.py`:

1. Add an import for the audio router and the audio store class:

```python
from api.routes_audio import (
    router as audio_router,
    get_audio_store,
)
from audio.store import AudioFileStore
```

2. Create a module-level audio store and override its dependency:

After the existing `file_store = ParsedFileStore()` line, add:

```python
audio_store = AudioFileStore()
```

After the existing `app.dependency_overrides[get_store] = lambda: file_store` line, add:

```python
app.dependency_overrides[get_audio_store] = lambda: audio_store
```

3. Add `app.include_router(audio_router)` after the existing router includes.

4. Update the `lifespan` function to create both audio cache directories. Replace its body with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    (DEFAULT_CACHE_DIR / "audio").mkdir(parents=True, exist_ok=True)
    (DEFAULT_CACHE_DIR / "midi" / "transcribed").mkdir(parents=True, exist_ok=True)
    yield
```

- [ ] **Step 3: Verify GREEN — full backend regression**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -q 2>&1 | tail -5`
Expected: every test passes including the new `test_audio_pipeline.py` (6 cases) and `test_routes_audio.py` (~8 cases).

- [ ] **Step 4: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/api/routes_audio.py backend/main.py && git commit -m "feat(api): /api/audio/search, /transcribe, /jobs routes"
```

---

## Task 7: Smoke test the running server

**Files:**
- None (verification only).

- [ ] **Step 1: Stop any prior uvicorn instance**

Run: `pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1; echo done`
Expected: `done`.

- [ ] **Step 2: Start the server**

Run in a background shell from `backend/`: `.venv/bin/uvicorn main:app --port 8000 --log-level warning &`. Give it 3 seconds to come up.

- [ ] **Step 3: Verify the new endpoints are registered**

Run: `curl -s http://localhost:8000/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print('\n'.join(sorted(p for p in d['paths'])))"`
Expected output includes:
```
/api/audio/jobs/{job_token}
/api/audio/search
/api/audio/transcribe
```
plus all the pre-existing routes.

- [ ] **Step 4: Stop the server**

Run: `pkill -f 'uvicorn main:app'`. No commit — verification only.

---

## Task 8: Plan-2 final regression

**Files:**
- None (verification only).

- [ ] **Step 1: Full test run**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected: all tests pass (existing + ~14 new from this plan).

- [ ] **Step 2: Confirm imports compose**

Run:
```bash
cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "
from api.routes_audio import router as audio_router
from audio.pipeline import run_transcribe_pipeline, TranscribeRequest
from main import app, audio_store
assert any('/api/audio' in str(r.path) for r in app.routes)
print('plan-2 ready')
"
```
Expected: `plan-2 ready`.

Plan 2 complete. Plan 3 covers the React frontend (mode toggle, audio search/upload UI, transcribe progress, README updates).

---

## What's NOT in this plan (intentionally deferred)

- **Frontend**: SearchPage mode toggle, AudioSearchSection, AudioCandidateCard, TranscribeProgress, client.js helpers — Plan 3.
- **README**: ffmpeg system dependency note, install size warning, personal-use disclaimer — Plan 3.
- **AUDIO_TOO_LONG enforcement**: the 10-minute duration cap from the spec is documented but not yet enforced. The download succeeds for any length; we'd need an extra `ffmpeg -i` probe step (or trust the source's `duration_seconds` from search metadata) to reject before transcription. Adding this is its own ~1-task chunk; defer to a polish task post-Plan-3 if real-world usage shows long uploads becoming a problem.
- **Real `audio_live` integration tests**: hitting real YouTube/Bilibili. The fixtures in plan 1 (slow tests) cover Basic Pitch realism; the route tests cover wiring. Live tests are markered but not implemented.
