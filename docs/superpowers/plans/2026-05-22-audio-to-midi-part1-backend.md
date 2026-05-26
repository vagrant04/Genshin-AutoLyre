# Audio-to-MIDI Pipeline — Plan 1: Backend audio package

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **DEVIATION (2026-05-23): NetEase dropped.** The original plan listed four platforms (YouTube, Bilibili, NetEase, QQ Music). `pyncm` is no longer published on PyPI, and the alternatives are too thin to wrap reliably. We ship three platforms only: **YouTube + Bilibili + QQ Music**. Concretely:
> - **Skip Task 11 entirely** (NetEaseSource).
> - The `AudioSourceKey` enum has THREE values: `YOUTUBE`, `BILIBILI`, `QQMUSIC`. Do NOT add `NETEASE`.
> - `requirements.txt` already has the working pins committed: `yt-dlp==2024.10.22`, `basic-pitch[onnx]>=0.3.0,<0.5`, `ffmpeg-python==0.2.0`, `qqmusic-api-python>=0.3.6,<0.4`. Do NOT add `pyncm`.
> - In Plan 2's route Literals and `_SOURCE_BY_PLATFORM` map, drop the `"netease"` entry.
> - In Plan 3's frontend platform radio, drop the "网易云" option.

**Goal:** Build the standalone backend audio package — dependency installation, `AbstractAudioSource` interface, three concrete source adapters (YouTube, Bilibili, QQ Music), the Basic Pitch transcriber wrapper, and an `AudioFileStore` for tracking transcription jobs. No FastAPI routes yet; this plan produces working, unit-tested Python modules that the next plan wires into HTTP routes.

**Architecture:** Each source is a thin adapter behind a single abstract base class — `search()` returns `AudioCandidate` lists, `fetch_to_path()` downloads to local disk. yt-dlp covers YouTube + Bilibili; qqmusic-api-python covers QQ Music. The transcriber lazy-loads the Basic Pitch TF-Lite model on first call and runs in a thread (sync API). All network failures bubble up as `SourceUnavailable`.

**Tech Stack:** Python 3.12, Pydantic v2 (already installed), yt-dlp, basic-pitch (with onnx extras), ffmpeg-python, qqmusic-api-python, pytest, pytest-asyncio. Builds on the existing `backend/` skeleton, `config.py` models, and the `BaseMusicSearcher` exception-swallowing pattern.

---

## File structure (this plan)

```
backend/
├── requirements.txt                        MODIFY (5 new deps)
├── config.py                               MODIFY (add AudioSourceKey enum + AudioCandidate + AudioMetadata models)
├── audio/
│   ├── __init__.py                         NEW (empty)
│   ├── exceptions.py                       NEW (SourceUnavailable, TranscriptionError, AudioTooLargeError, AudioTooLongError)
│   ├── sources/
│   │   ├── __init__.py                     NEW (empty)
│   │   ├── base.py                         NEW (AbstractAudioSource)
│   │   ├── youtube.py                      NEW
│   │   ├── bilibili.py                     NEW
│   │   ├── netease.py                      NEW
│   │   └── qqmusic.py                      NEW
│   ├── transcriber.py                      NEW (Basic Pitch wrapper)
│   └── store.py                            NEW (AudioFileStore — in-memory job tracking)
└── tests/
    ├── fixtures/
    │   └── ten_seconds_piano.mp3           NEW (committed CC0 piano clip)
    ├── test_audio_models.py                NEW
    ├── test_audio_sources_youtube.py       NEW
    ├── test_audio_sources_bilibili.py      NEW
    ├── test_audio_sources_netease.py       NEW
    ├── test_audio_sources_qqmusic.py       NEW
    ├── test_audio_transcriber.py           NEW (uses real Basic Pitch + fixture)
    └── test_audio_store.py                 NEW
```

**Responsibility split:**
- `audio/exceptions.py`: just exception classes; no logic.
- `audio/sources/base.py`: `AbstractAudioSource` ABC + helper for swallowing `search()` errors (mirrors `search/base.py` pattern).
- Each source file: one `Source` class, no other public API. Network calls only inside `_do_search()` and `fetch_to_path()`.
- `audio/transcriber.py`: a single `transcribe()` function plus a private `_get_model()` for lazy load.
- `audio/store.py`: tiny dict-backed registry — same shape as `api/store.py:ParsedFileStore` but typed for audio metadata.

---

## Task 1: Add audio dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Append the new dependencies**

Edit `backend/requirements.txt` and add five lines at the bottom (preserving existing pins):

```
yt-dlp==2024.10.22
basic-pitch==0.4.0
ffmpeg-python==0.2.0
pyncm==1.6.9.10
qqmusic-api-python==0.1.10
```

- [ ] **Step 2: Verify ffmpeg system binary**

Run: `which ffmpeg`
Expected: a path like `/opt/homebrew/bin/ffmpeg` or `/usr/local/bin/ffmpeg`. If missing on macOS, run `brew install ffmpeg` first; on Debian, `sudo apt install ffmpeg`.

- [ ] **Step 3: Install new deps into the existing venv**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pip install -r requirements.txt 2>&1 | tail -20`
Expected: pip resolves and installs `yt-dlp`, `basic-pitch`, `tensorflow` (transitive), `librosa` (transitive), `ffmpeg-python`, `pyncm`, `qqmusic-api-python`. May download ~500MB. Final line: `Successfully installed ...`.

- [ ] **Step 4: Smoke-import everything**

Run:
```bash
cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "
import yt_dlp
import basic_pitch
import ffmpeg
import pyncm
import qqmusic_api
print('all imports ok')
"
```
Expected: `all imports ok`. (Note: the qqmusic-api-python distribution exposes a `qqmusic_api` module — adjust the import to whatever the distribution actually exposes; if the import name differs, update the smoke check accordingly.)

- [ ] **Step 5: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/requirements.txt && git commit -m "chore(audio): add audio + transcription dependencies"
```

---

## Task 2: Add audio Pydantic models to config.py

**Files:**
- Modify: `backend/config.py`

- [ ] **Step 1: Append the audio models**

Open `backend/config.py` and append these models at the end of the file (after `ParsedMidi`):

```python
class AudioSourceKey(str, Enum):
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    NETEASE = "netease"
    QQMUSIC = "qqmusic"


class AudioCandidate(BaseModel):
    """One search result from any audio platform."""
    source: AudioSourceKey
    candidate_id: str          # platform-specific id (BV-id, video-id, song-id)
    title: str
    artist: Optional[str] = None
    duration_seconds: Optional[int] = None
    thumbnail_url: Optional[str] = None
    canonical_url: str          # what fetch_to_path consumes


class AudioMetadata(BaseModel):
    """Returned by fetch_to_path after a successful download."""
    source: AudioSourceKey
    canonical_url: str
    title: str
    duration_seconds: Optional[int] = None
    file_path: str              # absolute path on disk
    file_size_bytes: int
```

- [ ] **Step 2: Verify imports still work**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "from config import AudioCandidate, AudioMetadata, AudioSourceKey; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/config.py && git commit -m "feat(audio): AudioCandidate + AudioMetadata Pydantic models"
```

---

## Task 3: Audio exception types

**Files:**
- Create: `backend/audio/__init__.py` (empty)
- Create: `backend/audio/exceptions.py`

- [ ] **Step 1: Create empty package init**

Create `backend/audio/__init__.py` as an empty file.

- [ ] **Step 2: Write exceptions**

Create `backend/audio/exceptions.py`:

```python
"""Audio package exception hierarchy.

These are normal Python exceptions raised by the audio package; the
FastAPI route layer (next plan) maps them to ApiError codes from the
existing error catalog.
"""
from __future__ import annotations


class AudioError(Exception):
    """Base for all audio-pipeline errors."""


class SourceUnavailable(AudioError):
    """The source platform's API/library failed (paywall, region block,
    rate limit, broken upstream). User-facing message will be generic;
    `detail` carries the technical reason."""


class AudioTooLargeError(AudioError):
    """Audio file exceeded the 50 MB size cap."""


class AudioTooLongError(AudioError):
    """Audio duration exceeded the 10-minute cap."""


class TranscriptionError(AudioError):
    """Basic Pitch failed to transcribe (corrupt audio, OOM, etc.)."""


class InvalidAudioUrlError(AudioError):
    """URL host did not match any known source platform."""
```

- [ ] **Step 3: Verify import**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "from audio.exceptions import SourceUnavailable, TranscriptionError; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/__init__.py backend/audio/exceptions.py && git commit -m "feat(audio): exception hierarchy"
```

---

## Task 4: AbstractAudioSource base class + tests

**Files:**
- Create: `backend/audio/sources/__init__.py` (empty)
- Create: `backend/audio/sources/base.py`
- Create: `backend/tests/test_audio_models.py`

- [ ] **Step 1: Create empty subpackage init**

Create `backend/audio/sources/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_audio_models.py`:

```python
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
```

- [ ] **Step 3: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_models.py -v 2>&1 | tail -5`
Expected: `ModuleNotFoundError: No module named 'audio.sources.base'`.

- [ ] **Step 4: Write `audio/sources/base.py`**

```python
"""Abstract base class for audio sources.

Mirrors the pattern in `search/base.py`: subclasses implement
`_do_search()`, the public `search()` here swallows exceptions and
returns []. `fetch_to_path()` is defined directly by subclasses
because failure modes vary per platform (paywall vs rate-limit vs
region-block) and the route layer wants to surface them distinctly.
"""
from __future__ import annotations

import abc
import logging
from pathlib import Path

from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)


class AbstractAudioSource(abc.ABC):
    source: AudioSourceKey

    async def search(self, query: str, limit: int = 5) -> list[AudioCandidate]:
        try:
            return await self._do_search(query, limit)
        except Exception as exc:  # noqa: BLE001 — pattern from search/base.py
            _LOG.warning("audio search failed for %s: %s", self.source, exc)
            return []

    @abc.abstractmethod
    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        ...

    @abc.abstractmethod
    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        ...
```

- [ ] **Step 5: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_models.py -v 2>&1 | tail -5`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/sources/__init__.py backend/audio/sources/base.py backend/tests/test_audio_models.py && git commit -m "feat(audio): AbstractAudioSource base class + tests"
```

---

## Task 5: Commit a tiny CC0 piano fixture

**Files:**
- Create: `backend/tests/fixtures/ten_seconds_piano.mp3`

This fixture is only ~80 KB and unblocks the transcriber tests.

- [ ] **Step 1: Generate a synthetic piano fixture using mido + ffmpeg**

Generate a known MIDI then render to MP3 via ffmpeg's built-in `pluck` synth. Run:

```bash
cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python << 'PYEOF'
"""Build the 10s piano fixture from a hand-coded MIDI + ffmpeg.

We render a simple 4-quarter-note C major scale (C4 D4 E4 F4) at 120 BPM
into a wav using a sine generator, then transcode to mp3 with ffmpeg.
This avoids any third-party audio file commitments and gives the
transcriber tests deterministic input.
"""
import math, struct, subprocess, wave
from pathlib import Path

OUT = Path("tests/fixtures/ten_seconds_piano.mp3")
OUT.parent.mkdir(parents=True, exist_ok=True)
WAV = OUT.with_suffix(".wav")

sr = 22050
duration_s = 10
notes_per_s = 0.4   # 4 notes over 10 seconds
freqs = [261.63, 293.66, 329.63, 349.23, 392.00, 440.00, 493.88, 523.25] * 2  # C4..C5..C5
samples = []
for i in range(int(duration_s * sr)):
    t = i / sr
    note_i = min(int(t * notes_per_s), len(freqs) - 1)
    f = freqs[note_i]
    # Simple decaying sine "pluck"
    local_t = t - note_i / notes_per_s
    env = max(0.0, 1.0 - local_t * notes_per_s * 0.9)
    sample = int(0.4 * env * 32767 * math.sin(2 * math.pi * f * t))
    samples.append(sample)

with wave.open(str(WAV), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(sr)
    w.writeframes(b"".join(struct.pack("<h", s) for s in samples))

subprocess.run(
    ["ffmpeg", "-y", "-i", str(WAV), "-codec:a", "libmp3lame", "-b:a", "64k", str(OUT)],
    check=True, capture_output=True,
)
WAV.unlink()
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
PYEOF
```

Expected: `wrote tests/fixtures/ten_seconds_piano.mp3 (NNNN bytes)` where NNNN is somewhere around 80000.

- [ ] **Step 2: Verify the fixture**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "
from pathlib import Path
p = Path('tests/fixtures/ten_seconds_piano.mp3')
assert p.is_file() and 30_000 < p.stat().st_size < 200_000, f'unexpected size: {p.stat().st_size}'
print('fixture ok')
"`
Expected: `fixture ok`.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/tests/fixtures/ten_seconds_piano.mp3 && git commit -m "test(audio): synthetic 10s piano fixture for transcriber tests"
```

---

## Task 6: Transcriber — RED tests

**Files:**
- Create: `backend/tests/test_audio_transcriber.py`

- [ ] **Step 1: Write failing tests**

Note: the real Basic Pitch import is slow on first call (~30 s for TF lazy load). We mark these tests as `slow` so they can be skipped on default `pytest -q`. The test runner still exercises them via `pytest -m slow` or by name.

```python
"""Tests for audio.transcriber.

These tests exercise the real Basic Pitch transcription on the
fixture MP3 — the first run is slow because TensorFlow lazy-loads
the model (~30 s on CPU). Subsequent runs in the same process are
fast (~3 s for a 10-s clip).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import mido

from audio.exceptions import TranscriptionError
from audio.transcriber import transcribe

FIXTURE = Path(__file__).parent / "fixtures" / "ten_seconds_piano.mp3"


pytestmark = pytest.mark.slow


async def test_transcribes_to_midi(tmp_path: Path):
    out = tmp_path / "out.mid"
    result = await transcribe(FIXTURE, out)
    assert result == out
    assert out.is_file()
    assert out.stat().st_size > 0


async def test_output_midi_is_parseable(tmp_path: Path):
    out = tmp_path / "out.mid"
    await transcribe(FIXTURE, out)
    midi = mido.MidiFile(str(out))
    note_count = sum(
        1
        for track in midi.tracks
        for msg in track
        if msg.type == "note_on" and msg.velocity > 0
    )
    assert note_count > 0


async def test_transcribe_missing_file_raises(tmp_path: Path):
    bogus = tmp_path / "nope.mp3"
    out = tmp_path / "out.mid"
    with pytest.raises(TranscriptionError):
        await transcribe(bogus, out)
```

- [ ] **Step 2: Register the `slow` marker**

Edit `backend/pyproject.toml` to add a `markers` entry inside the existing `[tool.pytest.ini_options]` block. Replace the file contents with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
markers = [
    "slow: tests that take more than ~5 seconds (skipped by default; run with -m slow)",
    "audio_live: integration tests that touch real audio platforms",
]
```

- [ ] **Step 3: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_transcriber.py -m slow -v 2>&1 | tail -10`
Expected: `ModuleNotFoundError: No module named 'audio.transcriber'`.

- [ ] **Step 4: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/tests/test_audio_transcriber.py backend/pyproject.toml && git commit -m "test(audio): transcriber spec tests + slow/audio_live markers"
```

---

## Task 7: Transcriber implementation (GREEN)

**Files:**
- Create: `backend/audio/transcriber.py`

- [ ] **Step 1: Write the wrapper**

Basic Pitch's official API is `basic_pitch.inference.predict_and_save([audio_path], output_dir, save_midi=True, ...)` which writes one or more files into `output_dir`. We invoke it in a thread because the call is sync + CPU-bound, then move the produced `*_basic_pitch.mid` to the requested output path.

```python
"""Basic Pitch transcription wrapper.

Spec: docs/superpowers/specs/2026-05-22-audio-to-midi-design.md.

The Basic Pitch model is heavy (~30 s lazy-load on first run). We let
TensorFlow handle that internally on the first `transcribe()` call;
subsequent calls in the same process are fast.

We invoke Basic Pitch in a thread to keep the FastAPI event loop
responsive (Basic Pitch is sync + CPU-bound).
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from audio.exceptions import TranscriptionError

_LOG = logging.getLogger(__name__)


# Sensitivity → onset_threshold mapping.
SENSITIVITY_PRESETS: dict[str, float] = {
    "low": 0.7,
    "medium": 0.5,
    "high": 0.3,
}

DEFAULT_MIN_NOTE_LENGTH_MS = 60


async def transcribe(
    audio_path: Path,
    midi_out_path: Path,
    *,
    onset_threshold: float = 0.5,
    min_note_length_ms: int = DEFAULT_MIN_NOTE_LENGTH_MS,
) -> Path:
    """Transcribe `audio_path` to `midi_out_path` via Basic Pitch.

    Returns the output path on success. Raises TranscriptionError on any
    failure (missing input, decoder error, model crash).
    """
    if not audio_path.is_file():
        raise TranscriptionError(f"audio file not found: {audio_path}")
    midi_out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        await asyncio.to_thread(
            _run_basic_pitch,
            audio_path,
            midi_out_path,
            onset_threshold,
            min_note_length_ms,
        )
    except TranscriptionError:
        raise
    except Exception as exc:  # noqa: BLE001 — convert any failure
        raise TranscriptionError(f"basic-pitch failed: {exc}") from exc
    if not midi_out_path.is_file() or midi_out_path.stat().st_size == 0:
        raise TranscriptionError("basic-pitch produced no output")
    return midi_out_path


def _run_basic_pitch(
    audio_path: Path,
    midi_out_path: Path,
    onset_threshold: float,
    min_note_length_ms: int,
) -> None:
    """Sync helper, called via asyncio.to_thread."""
    # Import here so the module can be loaded without TF installed
    # (e.g. during light unit tests).
    from basic_pitch.inference import predict_and_save
    from basic_pitch import ICASSP_2022_MODEL_PATH

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        predict_and_save(
            audio_path_list=[str(audio_path)],
            output_directory=str(tmp_dir),
            save_midi=True,
            sonify_midi=False,
            save_model_outputs=False,
            save_notes=False,
            model_or_model_path=ICASSP_2022_MODEL_PATH,
            onset_threshold=onset_threshold,
            minimum_note_length=min_note_length_ms,
        )
        produced = list(tmp_dir.glob("*_basic_pitch.mid"))
        if not produced:
            raise TranscriptionError(
                "basic-pitch did not produce a .mid output"
            )
        shutil.move(str(produced[0]), str(midi_out_path))
```

- [ ] **Step 2: Run the slow tests**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_transcriber.py -m slow -v 2>&1 | tail -15`
Expected: 3 tests PASS. The first test runs 30-60 s; the other two are fast because TF stays loaded.

- [ ] **Step 3: Confirm fast suite still green**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected: same passing count as before this plan started, plus the 3 new fast tests from Task 4 (so existing+3). Slow tests are skipped by default.

- [ ] **Step 4: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/transcriber.py && git commit -m "feat(audio): Basic Pitch transcriber wrapper"
```

---

## Task 8: YouTube source — RED tests

**Files:**
- Create: `backend/tests/test_audio_sources_youtube.py`

- [ ] **Step 1: Write failing tests**

We cannot mock yt-dlp's network calls cleanly because its `YoutubeDL.extract_info` is a complex blocking method, but we can replace it on the searcher instance via dependency injection: each source accepts an optional `extractor_factory` we substitute in tests.

```python
"""Tests for YouTubeSource. yt-dlp's extract_info is replaced by a
pure-python stub (no network)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.youtube import YouTubeSource
from config import AudioSourceKey


# yt-dlp's extract_info on a search query returns:
#   {"entries": [ {video_dict}, ... ]}
# On a single URL it returns the video_dict directly. We model both.

_VIDEO_1 = {
    "id": "abc123",
    "title": "Twinkle piano cover",
    "uploader": "Anon",
    "duration": 180,
    "thumbnail": "https://yt/abc123.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
}
_VIDEO_2 = {
    "id": "def456",
    "title": "Another song",
    "uploader": "Anon2",
    "duration": 240,
    "thumbnail": "https://yt/def456.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=def456",
}


class _StubYDL:
    """Drop-in for yt_dlp.YoutubeDL within a `with` block."""

    def __init__(self, params: dict[str, Any]):
        self.params = params
        self.calls: list[tuple[str, bool]] = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, query: str, download: bool):
        self.calls.append((query, download))
        if query.startswith("ytsearch"):
            return {"entries": [_VIDEO_1, _VIDEO_2]}
        if query == "https://www.youtube.com/watch?v=abc123":
            if download:
                # Pretend yt-dlp wrote the audio at the requested path.
                Path(self.params["outtmpl"]).write_bytes(b"FAKE_MP3")
            return _VIDEO_1
        raise RuntimeError(f"unexpected query: {query}")


def _factory(*args, **kwargs):
    return _StubYDL(kwargs.get("params", {}) if kwargs else (args[0] if args else {}))


async def test_search_returns_candidates():
    src = YouTubeSource(ydl_factory=_factory)
    out = await src.search("twinkle", limit=5)
    assert len(out) == 2
    assert out[0].source == AudioSourceKey.YOUTUBE
    assert out[0].candidate_id == "abc123"
    assert "Twinkle" in out[0].title
    assert out[0].duration_seconds == 180
    assert out[0].canonical_url.endswith("v=abc123")


async def test_fetch_writes_audio(tmp_path: Path):
    src = YouTubeSource(ydl_factory=_factory)
    target = tmp_path / "yt_abc123.mp3"
    meta = await src.fetch_to_path(
        "https://www.youtube.com/watch?v=abc123", target
    )
    assert target.is_file()
    assert meta.title == "Twinkle piano cover"
    assert meta.source == AudioSourceKey.YOUTUBE
    assert meta.file_size_bytes > 0


async def test_fetch_propagates_extractor_failure_as_unavailable(tmp_path: Path):
    class _FailingYDL:
        def __init__(self, params): self.params = params
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, q, download):
            raise RuntimeError("yt-dlp blew up")

    src = YouTubeSource(ydl_factory=lambda *a, **kw: _FailingYDL(kw or a))
    with pytest.raises(SourceUnavailable):
        await src.fetch_to_path(
            "https://www.youtube.com/watch?v=abc123", tmp_path / "x.mp3"
        )
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_youtube.py -v 2>&1 | tail -5`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/tests/test_audio_sources_youtube.py && git commit -m "test(audio): YouTube source spec tests (RED)"
```

---

## Task 9: YouTubeSource implementation

**Files:**
- Create: `backend/audio/sources/youtube.py`

- [ ] **Step 1: Write the source**

```python
"""YouTube audio source via yt-dlp.

`search()` uses the `ytsearch{N}:` prefix; `fetch_to_path()` does a
single-URL extract with `bestaudio` and writes the audio to the
provided target path.

`ydl_factory` is injected so tests can substitute a stub. In production,
use the default factory which returns a real `yt_dlp.YoutubeDL`.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)


def _default_factory(params: dict[str, Any]):
    import yt_dlp  # noqa: WPS433 — local import keeps top-level cheap
    return yt_dlp.YoutubeDL(params)


class YouTubeSource(AbstractAudioSource):
    source = AudioSourceKey.YOUTUBE

    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_factory,
    ) -> None:
        self._factory = ydl_factory

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        params = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "default_search": "ytsearch",
        }
        info = await asyncio.to_thread(
            self._extract, params, f"ytsearch{limit}:{query}", False
        )
        entries = (info or {}).get("entries") or []
        out: list[AudioCandidate] = []
        for e in entries[:limit]:
            if not isinstance(e, dict):
                continue
            vid = e.get("id") or ""
            if not vid:
                continue
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=vid,
                    title=str(e.get("title") or "Untitled"),
                    artist=e.get("uploader"),
                    duration_seconds=e.get("duration"),
                    thumbnail_url=e.get("thumbnail"),
                    canonical_url=e.get("webpage_url")
                    or f"https://www.youtube.com/watch?v={vid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.parent.mkdir(parents=True, exist_ok=True)
        params = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(target),
            "noplaylist": True,
            # yt-dlp will rename the output if it doesn't like the suffix.
            "postprocessors": [],
        }
        try:
            info = await asyncio.to_thread(self._extract, params, url, True)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"yt-dlp failed: {exc}") from exc
        if not target.is_file():
            raise SourceUnavailable(
                "yt-dlp did not produce the expected output file"
            )
        return AudioMetadata(
            source=self.source,
            canonical_url=str((info or {}).get("webpage_url") or url),
            title=str((info or {}).get("title") or target.stem),
            duration_seconds=(info or {}).get("duration"),
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )

    def _extract(
        self,
        params: dict[str, Any],
        query: str,
        download: bool,
    ) -> dict[str, Any] | None:
        try:
            with self._factory(params) as ydl:
                return ydl.extract_info(query, download=download)
        except Exception as exc:  # noqa: BLE001
            # Re-raise as SourceUnavailable when called from fetch path;
            # _do_search() callers already swallow into [].
            raise SourceUnavailable(str(exc)) from exc
```

- [ ] **Step 2: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_youtube.py -v 2>&1 | tail -5`
Expected: 3 tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/sources/youtube.py && git commit -m "feat(audio): YouTubeSource via yt-dlp"
```

---

## Task 10: BilibiliSource — tests + impl

**Files:**
- Create: `backend/tests/test_audio_sources_bilibili.py`
- Create: `backend/audio/sources/bilibili.py`

The implementation mirrors YouTube but uses `bilisearch{N}:` and the Bilibili URL pattern. yt-dlp's BilibiliExtractor handles authentication via a Sessdata cookie if present in the env (`BILI_SESSDATA`).

- [ ] **Step 1: Write failing tests**

```python
"""Tests for BilibiliSource."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.bilibili import BilibiliSource
from config import AudioSourceKey


_VIDEO = {
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
        if q.startswith("bilisearch"):
            return {"entries": [_VIDEO]}
        if q == "https://www.bilibili.com/video/BV1xx":
            if download:
                Path(self.params["outtmpl"]).write_bytes(b"BILI_AUDIO")
            return _VIDEO
        raise RuntimeError(f"unexpected: {q}")


def _factory(params): return _StubYDL(params)


async def test_search_uses_bilisearch_prefix():
    captured = []

    class _Capture(_StubYDL):
        def extract_info(self, q, download):
            captured.append(q)
            return super().extract_info(q, download)

    src = BilibiliSource(ydl_factory=lambda p: _Capture(p))
    await src.search("晴天", limit=3)
    assert captured and captured[0].startswith("bilisearch3:")


async def test_search_returns_candidates():
    src = BilibiliSource(ydl_factory=_factory)
    out = await src.search("晴天", limit=3)
    assert len(out) == 1
    assert out[0].source == AudioSourceKey.BILIBILI
    assert out[0].candidate_id == "BV1xx"
    assert "BV1xx" in out[0].canonical_url


async def test_fetch_writes_audio(tmp_path: Path):
    src = BilibiliSource(ydl_factory=_factory)
    out = tmp_path / "x.m4a"
    meta = await src.fetch_to_path(
        "https://www.bilibili.com/video/BV1xx", out
    )
    assert out.is_file()
    assert meta.source == AudioSourceKey.BILIBILI
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_bilibili.py -v 2>&1 | tail -5`
Expected: import error.

- [ ] **Step 3: Write the source**

```python
"""Bilibili audio source via yt-dlp's BilibiliExtractor."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Callable

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)


def _default_factory(params: dict[str, Any]):
    import yt_dlp  # noqa: WPS433
    return yt_dlp.YoutubeDL(params)


class BilibiliSource(AbstractAudioSource):
    source = AudioSourceKey.BILIBILI

    def __init__(
        self,
        *,
        ydl_factory: Callable[[dict[str, Any]], Any] = _default_factory,
    ) -> None:
        self._factory = ydl_factory

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        params = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": "in_playlist",
        }
        info = await asyncio.to_thread(
            self._extract, params, f"bilisearch{limit}:{query}", False
        )
        entries = (info or {}).get("entries") or []
        out: list[AudioCandidate] = []
        for e in entries[:limit]:
            if not isinstance(e, dict):
                continue
            bvid = e.get("id") or ""
            if not bvid:
                continue
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=bvid,
                    title=str(e.get("title") or "Untitled"),
                    artist=e.get("uploader"),
                    duration_seconds=e.get("duration"),
                    thumbnail_url=e.get("thumbnail"),
                    canonical_url=e.get("webpage_url")
                    or f"https://www.bilibili.com/video/{bvid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        target.parent.mkdir(parents=True, exist_ok=True)
        params: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(target),
            "noplaylist": True,
        }
        sessdata = os.environ.get("BILI_SESSDATA")
        if sessdata:
            params["http_headers"] = {"Cookie": f"SESSDATA={sessdata}"}
        try:
            info = await asyncio.to_thread(self._extract, params, url, True)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"yt-dlp/bilibili failed: {exc}") from exc
        if not target.is_file():
            raise SourceUnavailable(
                "yt-dlp/bilibili did not produce expected output"
            )
        return AudioMetadata(
            source=self.source,
            canonical_url=str((info or {}).get("webpage_url") or url),
            title=str((info or {}).get("title") or target.stem),
            duration_seconds=(info or {}).get("duration"),
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )

    def _extract(
        self,
        params: dict[str, Any],
        query: str,
        download: bool,
    ) -> dict[str, Any] | None:
        try:
            with self._factory(params) as ydl:
                return ydl.extract_info(query, download=download)
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(str(exc)) from exc
```

- [ ] **Step 4: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_bilibili.py -v 2>&1 | tail -5`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/sources/bilibili.py backend/tests/test_audio_sources_bilibili.py && git commit -m "feat(audio): BilibiliSource via yt-dlp"
```

---

## Task 11: NetEaseSource — tests + impl

**Files:**
- Create: `backend/tests/test_audio_sources_netease.py`
- Create: `backend/audio/sources/netease.py`

The pyncm library's main entrypoints are `pyncm.apis.cloudsearch.GetSearchResult(keyword, ...)` for search and `pyncm.apis.track.GetTrackAudio([song_id], ...)` for download URLs. Both raise on failure. We inject a `client` so tests can substitute.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for NetEaseSource. pyncm calls are replaced with stubs."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from audio.exceptions import SourceUnavailable
from audio.sources.netease import NetEaseSource
from config import AudioSourceKey


class _StubClient:
    def __init__(self, search_result, audio_url, http_payload=b"NE_AUDIO"):
        self._search = search_result
        self._audio_url = audio_url
        self._http_payload = http_payload

    def search(self, keyword, limit):
        return self._search

    def get_audio_url(self, song_id):
        return self._audio_url

    async def download(self, url, target: Path):
        target.write_bytes(self._http_payload)


_SEARCH_OK = {
    "result": {
        "songs": [
            {
                "id": 12345,
                "name": "晴天",
                "ar": [{"name": "周杰伦"}],
                "dt": 250000,  # ms
                "al": {"picUrl": "https://p1/a.jpg"},
            }
        ]
    }
}


async def test_search_returns_candidates():
    src = NetEaseSource(client=_StubClient(_SEARCH_OK, audio_url=None))
    out = await src.search("晴天", limit=5)
    assert len(out) == 1
    assert out[0].source == AudioSourceKey.NETEASE
    assert out[0].candidate_id == "12345"
    assert out[0].duration_seconds == 250  # ms → s


async def test_search_returns_empty_when_no_songs():
    src = NetEaseSource(client=_StubClient({"result": {"songs": []}}, audio_url=None))
    out = await src.search("x", limit=5)
    assert out == []


async def test_fetch_raises_when_audio_url_paywalled(tmp_path: Path):
    src = NetEaseSource(
        client=_StubClient(_SEARCH_OK, audio_url=None)
    )
    with pytest.raises(SourceUnavailable):
        await src.fetch_to_path(
            "https://music.163.com/song?id=12345", tmp_path / "out.mp3"
        )


async def test_fetch_writes_audio(tmp_path: Path):
    src = NetEaseSource(
        client=_StubClient(
            _SEARCH_OK,
            audio_url="https://m7.music.126.net/whatever.mp3",
        )
    )
    target = tmp_path / "out.mp3"
    meta = await src.fetch_to_path(
        "https://music.163.com/song?id=12345", target
    )
    assert target.is_file()
    assert meta.source == AudioSourceKey.NETEASE
    assert meta.title  # populated from id resolution
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_netease.py -v 2>&1 | tail -5`
Expected: import error.

- [ ] **Step 3: Write the source**

```python
"""NetEase Cloud Music audio source.

Wraps the pyncm community library. Many tracks return only a 30-second
preview or a 403 outside China; we surface those as SourceUnavailable.

The `client` parameter exists so tests can substitute the network
calls. Production code uses `_DefaultClient`, which lazy-imports pyncm.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)
_SONG_ID_RE = re.compile(r"id=(\d+)")


class _ClientProtocol(Protocol):
    def search(self, keyword: str, limit: int) -> dict[str, Any]: ...
    def get_audio_url(self, song_id: str) -> Optional[str]: ...
    async def download(self, url: str, target: Path) -> None: ...


class _DefaultClient:
    """Production client backed by pyncm + httpx."""

    def search(self, keyword: str, limit: int) -> dict[str, Any]:
        from pyncm.apis.cloudsearch import GetSearchResult  # noqa: WPS433
        return GetSearchResult(keyword=keyword, stype=1, limit=limit)

    def get_audio_url(self, song_id: str) -> Optional[str]:
        from pyncm.apis.track import GetTrackAudio  # noqa: WPS433
        result = GetTrackAudio([int(song_id)])
        data = (result or {}).get("data") or []
        if not data:
            return None
        return data[0].get("url") or None

    async def download(self, url: str, target: Path) -> None:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
            async with c.stream("GET", url) as r:
                if r.status_code != 200:
                    raise SourceUnavailable(f"netease audio HTTP {r.status_code}")
                with target.open("wb") as fh:
                    async for chunk in r.aiter_bytes():
                        fh.write(chunk)


class NetEaseSource(AbstractAudioSource):
    source = AudioSourceKey.NETEASE

    def __init__(self, *, client: Optional[_ClientProtocol] = None) -> None:
        self._client = client or _DefaultClient()

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        result = await asyncio.to_thread(self._client.search, query, limit)
        songs = (((result or {}).get("result") or {}).get("songs")) or []
        out: list[AudioCandidate] = []
        for s in songs[:limit]:
            sid = str(s.get("id") or "")
            if not sid:
                continue
            artists = s.get("ar") or s.get("artists") or []
            artist = artists[0].get("name") if artists else None
            duration_ms = s.get("dt") or s.get("duration") or 0
            thumb = ((s.get("al") or s.get("album") or {}).get("picUrl"))
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=sid,
                    title=str(s.get("name") or "Untitled"),
                    artist=artist,
                    duration_seconds=int(duration_ms / 1000) if duration_ms else None,
                    thumbnail_url=thumb,
                    canonical_url=f"https://music.163.com/song?id={sid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        match = _SONG_ID_RE.search(url)
        if not match:
            raise SourceUnavailable(f"cannot extract NetEase song id from {url}")
        song_id = match.group(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            audio_url = await asyncio.to_thread(
                self._client.get_audio_url, song_id
            )
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"pyncm get_audio_url failed: {exc}") from exc
        if not audio_url:
            raise SourceUnavailable(
                "track requires login or is paywalled / region-blocked"
            )
        try:
            await self._client.download(audio_url, target)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"netease download failed: {exc}") from exc
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title=f"NetEase {song_id}",  # full title via separate API call is YAGNI
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )
```

- [ ] **Step 4: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_netease.py -v 2>&1 | tail -5`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/sources/netease.py backend/tests/test_audio_sources_netease.py && git commit -m "feat(audio): NetEaseSource via pyncm"
```

---

## Task 12: QQMusicSource — tests + impl

**Files:**
- Create: `backend/tests/test_audio_sources_qqmusic.py`
- Create: `backend/audio/sources/qqmusic.py`

Same shape as NetEase.

- [ ] **Step 1: Write failing tests**

```python
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
                    "interval": 250,  # seconds
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
```

- [ ] **Step 2: Write the source**

```python
"""QQ Music audio source.

Wraps the qqmusic-api-python community library. Most tracks are
paywalled; we surface those as SourceUnavailable.
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Optional, Protocol

import httpx

from audio.exceptions import SourceUnavailable
from audio.sources.base import AbstractAudioSource
from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)
_MID_RE = re.compile(r"songDetail/([A-Za-z0-9]+)")


class _ClientProtocol(Protocol):
    def search(self, keyword: str, limit: int) -> dict[str, Any]: ...
    def get_audio_url(self, song_mid: str) -> Optional[str]: ...
    async def download(self, url: str, target: Path) -> None: ...


class _DefaultClient:
    def search(self, keyword: str, limit: int) -> dict[str, Any]:
        # The real API surface for qqmusic-api-python varies by version;
        # this default implementation may need updating when the library
        # is bumped.
        from qqmusic_api import search as qsearch  # noqa: WPS433
        return qsearch.search_by_type(keyword, num=limit)

    def get_audio_url(self, song_mid: str) -> Optional[str]:
        from qqmusic_api import song as qsong  # noqa: WPS433
        urls = qsong.get_song_urls([song_mid])
        return urls.get(song_mid) if isinstance(urls, dict) else None

    async def download(self, url: str, target: Path) -> None:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
            async with c.stream("GET", url) as r:
                if r.status_code != 200:
                    raise SourceUnavailable(f"qq HTTP {r.status_code}")
                with target.open("wb") as fh:
                    async for chunk in r.aiter_bytes():
                        fh.write(chunk)


class QQMusicSource(AbstractAudioSource):
    source = AudioSourceKey.QQMUSIC

    def __init__(self, *, client: Optional[_ClientProtocol] = None) -> None:
        self._client = client or _DefaultClient()

    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        result = await asyncio.to_thread(self._client.search, query, limit)
        songs = (((result or {}).get("data") or {}).get("song") or {}).get("list") or []
        out: list[AudioCandidate] = []
        for s in songs[:limit]:
            mid = str(s.get("songmid") or s.get("mid") or "")
            if not mid:
                continue
            singers = s.get("singer") or []
            artist = singers[0].get("name") if singers else None
            interval = s.get("interval")  # seconds
            out.append(
                AudioCandidate(
                    source=self.source,
                    candidate_id=mid,
                    title=str(s.get("songname") or s.get("title") or "Untitled"),
                    artist=artist,
                    duration_seconds=int(interval) if interval else None,
                    thumbnail_url=None,
                    canonical_url=f"https://y.qq.com/n/ryqq/songDetail/{mid}",
                )
            )
        return out

    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        match = _MID_RE.search(url)
        if not match:
            raise SourceUnavailable(f"cannot extract QQ song mid from {url}")
        mid = match.group(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            audio_url = await asyncio.to_thread(self._client.get_audio_url, mid)
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"qq get_audio_url failed: {exc}") from exc
        if not audio_url:
            raise SourceUnavailable(
                "QQ track requires VIP / payment or is region-blocked"
            )
        try:
            await self._client.download(audio_url, target)
        except SourceUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise SourceUnavailable(f"qq download failed: {exc}") from exc
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title=f"QQ {mid}",
            file_path=str(target),
            file_size_bytes=target.stat().st_size,
        )
```

- [ ] **Step 3: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_sources_qqmusic.py -v 2>&1 | tail -5`
Expected: 3 tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/sources/qqmusic.py backend/tests/test_audio_sources_qqmusic.py && git commit -m "feat(audio): QQMusicSource via qqmusic-api-python"
```

---

## Task 13: AudioFileStore (in-memory job tracking)

**Files:**
- Create: `backend/audio/store.py`
- Create: `backend/tests/test_audio_store.py`

Tracks transcription jobs by token: stage (`downloading|transcribing|done|error`), error message, and the resulting `file_token` from the parse pipeline once done. The next plan's HTTP route uses this so the frontend can poll a status endpoint.

- [ ] **Step 1: Write failing tests**

```python
"""Tests for AudioFileStore."""
from __future__ import annotations

from audio.store import AudioFileStore, JobStage


def test_create_returns_token_with_prefix():
    store = AudioFileStore()
    token = store.create_job()
    assert token.startswith("aud_")


def test_get_returns_initial_state():
    store = AudioFileStore()
    token = store.create_job()
    job = store.get(token)
    assert job.stage == JobStage.QUEUED
    assert job.error is None
    assert job.parse_token is None


def test_update_stage():
    store = AudioFileStore()
    token = store.create_job()
    store.update(token, stage=JobStage.DOWNLOADING)
    assert store.get(token).stage == JobStage.DOWNLOADING


def test_complete_with_parse_token():
    store = AudioFileStore()
    token = store.create_job()
    store.update(token, stage=JobStage.DONE, parse_token="tmp_xyz")
    job = store.get(token)
    assert job.stage == JobStage.DONE
    assert job.parse_token == "tmp_xyz"


def test_get_unknown_raises_keyerror():
    store = AudioFileStore()
    import pytest
    with pytest.raises(KeyError):
        store.get("aud_nope")


def test_update_unknown_raises_keyerror():
    store = AudioFileStore()
    import pytest
    with pytest.raises(KeyError):
        store.update("aud_nope", stage=JobStage.DONE)
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_store.py -v 2>&1 | tail -5`
Expected: import error.

- [ ] **Step 3: Write the store**

```python
"""In-memory tracking of audio transcription jobs.

Each job represents one /api/audio/transcribe request lifecycle:
download → transcribe → parse. The next plan's route updates the job
as it progresses so the frontend can poll for stage changes.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    PARSING = "parsing"
    DONE = "done"
    ERROR = "error"


@dataclass
class AudioJob:
    stage: JobStage = JobStage.QUEUED
    error: Optional[str] = None
    parse_token: Optional[str] = None  # set once the pipeline completes


class AudioFileStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AudioJob] = {}

    def create_job(self) -> str:
        token = f"aud_{secrets.token_hex(8)}"
        self._jobs[token] = AudioJob()
        return token

    def get(self, token: str) -> AudioJob:
        return self._jobs[token]

    def update(
        self,
        token: str,
        *,
        stage: Optional[JobStage] = None,
        error: Optional[str] = None,
        parse_token: Optional[str] = None,
    ) -> None:
        job = self._jobs[token]  # raises KeyError if unknown
        if stage is not None:
            job.stage = stage
        if error is not None:
            job.error = error
        if parse_token is not None:
            job.parse_token = parse_token
```

- [ ] **Step 4: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_audio_store.py -v 2>&1 | tail -5`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/audio/store.py backend/tests/test_audio_store.py && git commit -m "feat(audio): AudioFileStore for tracking transcription jobs"
```

---

## Task 14: Plan-1 final regression

**Files:**
- None (verification only).

- [ ] **Step 1: Run the full backend test suite**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected: every existing test plus the new fast tests from this plan pass. Slow tests (`test_audio_transcriber.py`) are skipped by default.

- [ ] **Step 2: Optional — run the slow transcriber tests**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -m slow -v 2>&1 | tail -10`
Expected: 3 transcriber tests PASS. First run takes 30-60 s (TF lazy load).

- [ ] **Step 3: Confirm package-level imports compose cleanly**

Run:
```bash
cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -c "
from audio.sources.youtube import YouTubeSource
from audio.sources.bilibili import BilibiliSource
from audio.sources.netease import NetEaseSource
from audio.sources.qqmusic import QQMusicSource
from audio.transcriber import transcribe, SENSITIVITY_PRESETS
from audio.store import AudioFileStore, JobStage
from audio.exceptions import SourceUnavailable, TranscriptionError
print('plan-1 ready')
"
```
Expected: `plan-1 ready`.

Plan 1 complete. Plan 2 will wire these into FastAPI routes (`/api/audio/search`, `/api/audio/transcribe`, `/api/audio/jobs/{token}`); Plan 3 covers the React frontend.

---

## What's NOT in this plan (intentionally deferred)

- **FastAPI routes** for `/api/audio/*` — Plan 2.
- **Frontend mode toggle, AudioSearchSection, AudioCandidateCard, TranscribeProgress** — Plan 3.
- **README updates** for the new system dependency (ffmpeg) and install size note — Plan 3 includes the README diff.
- **`pyproject.toml` `[project.optional-dependencies]`** for an `audio` extras group — design spec rejected this in favor of single-requirements (see spec §"How heavy should the install footprint be?"). Sticking with the decision.
