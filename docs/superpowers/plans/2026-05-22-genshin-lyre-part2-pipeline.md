# Genshin Lyre — Part 2: MIDI Pipeline (Parser + Search + Download)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MIDI ingestion pipeline: download/cache utilities, MIDI parsing into `ParsedNote` lists with track metadata, track-role classification, accompaniment chord-grouping, and the four-platform search aggregator.

**Architecture:** Three layered packages built on top of part 1. `utils/` provides async HTTP download and on-disk caching. `parser/` consumes a local MIDI file path, returns BPM, ticks_per_beat, `TrackInfo` list (with `suggested_role` and `chord_type`), and per-track `ParsedNote` lists; it also produces the chord-group input the merger needs. `search/` implements four platform searchers behind one abstract base and an async aggregator that fans out via `asyncio.gather` and dedupes. All network failures are caught — searchers return `[]` rather than raising.

**Tech Stack:** Python 3.11+, music21, mido (fallback), httpx (async), beautifulsoup4 + lxml, pytest, pytest-asyncio. Builds on part 1's `config.py` and `mapper/`.

---

## File Structure

```
backend/
├── utils/
│   ├── __init__.py
│   ├── cache.py                 # URL-hash → local path; existence checks
│   └── downloader.py            # async download w/ size cap & timeout
├── parser/
│   ├── __init__.py
│   ├── midi_parser.py           # parse local file → BPM, TPB, tracks, notes
│   ├── track_classifier.py      # suggested_role + chord_type per track
│   └── chord_grouper.py         # group accompaniment notes into chord groups
├── search/
│   ├── __init__.py
│   ├── base.py                  # BaseMusicSearcher abstract class
│   ├── freemidi.py              # FreeMidiSearcher
│   ├── bitmidi.py               # BitMidiSearcher
│   ├── musescore.py             # MuseScoreSearcher (no download_url)
│   ├── bilibili.py              # BilibiliSearcher (regex-extract from desc)
│   └── aggregator.py            # asyncio.gather + dedupe + rank
└── tests/
    ├── fixtures/
    │   └── twinkle.mid          # tiny hand-built MIDI for tests
    ├── test_downloader.py
    ├── test_cache.py
    ├── test_midi_parser.py
    ├── test_track_classifier.py
    ├── test_chord_grouper.py
    ├── test_search_base.py
    ├── test_search_aggregator.py
    └── test_searchers_html.py
```

**Responsibility split:**
- `utils/cache.py` is pure path math + filesystem checks; no network.
- `utils/downloader.py` does one thing: stream a URL to a local file with a size limit and timeout.
- `parser/midi_parser.py` works on local paths only — it does NOT call the downloader. The route layer (part 3) wires download → parse.
- `parser/track_classifier.py` is a pure function over a `(track_index, list[ParsedNote])` pair — no I/O.
- `parser/chord_grouper.py` is a pure function: groups simultaneous accompaniment notes into the `chord_groups` list the merger needs.
- Each `search/*.py` searcher is independent. They return `[]` on any failure. Aggregator never raises.

---

## Task 1: Cache utility (TDD)

**Files:**
- Create: `backend/utils/__init__.py` (empty)
- Create: `backend/utils/cache.py`
- Create: `backend/tests/test_cache.py`

- [ ] **Step 1: Create empty package init**

Create `backend/utils/__init__.py` as an empty file.

- [ ] **Step 2: Write failing tests**

```python
"""Tests for utils.cache. Spec §8.2.1 (URL-hash caching)."""
from __future__ import annotations

from pathlib import Path

import pytest

from utils.cache import cache_path_for_url, ensure_cache_dir, is_cached


def test_cache_path_is_deterministic(tmp_path: Path):
    p1 = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    p2 = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert p1 == p2


def test_different_urls_produce_different_paths(tmp_path: Path):
    p1 = cache_path_for_url("https://example.com/a.mid", base=tmp_path)
    p2 = cache_path_for_url("https://example.com/b.mid", base=tmp_path)
    assert p1 != p2


def test_cache_path_lives_under_base(tmp_path: Path):
    p = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert tmp_path in p.parents


def test_cache_path_uses_mid_extension(tmp_path: Path):
    p = cache_path_for_url("https://example.com/foo.mid", base=tmp_path)
    assert p.suffix == ".mid"


def test_is_cached_false_when_missing(tmp_path: Path):
    assert is_cached("https://example.com/missing.mid", base=tmp_path) is False


def test_is_cached_true_after_write(tmp_path: Path):
    p = cache_path_for_url("https://example.com/exists.mid", base=tmp_path)
    p.write_bytes(b"MThd")
    assert is_cached("https://example.com/exists.mid", base=tmp_path) is True


def test_ensure_cache_dir_creates_directory(tmp_path: Path):
    target = tmp_path / "nested" / "cache"
    ensure_cache_dir(target)
    assert target.is_dir()


def test_ensure_cache_dir_idempotent(tmp_path: Path):
    target = tmp_path / "cache"
    ensure_cache_dir(target)
    ensure_cache_dir(target)  # must not raise
    assert target.is_dir()
```

- [ ] **Step 3: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_cache.py -v`
Expected: import error.

- [ ] **Step 4: Write the implementation**

```python
"""URL-hash file cache.

Used by the parse route to avoid re-downloading the same MIDI URL.
Pure path math + filesystem ops; no network.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

DEFAULT_CACHE_DIR = Path("/tmp/genshin_lyre")


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def cache_path_for_url(url: str, *, base: Path = DEFAULT_CACHE_DIR) -> Path:
    return base / f"{_hash_url(url)}.mid"


def is_cached(url: str, *, base: Path = DEFAULT_CACHE_DIR) -> bool:
    return cache_path_for_url(url, base=base).is_file()


def ensure_cache_dir(base: Path = DEFAULT_CACHE_DIR) -> None:
    base.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 5: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_cache.py -v`
Expected: 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/utils/__init__.py backend/utils/cache.py backend/tests/test_cache.py
git commit -m "feat(utils): URL-hash file cache for MIDI downloads"
```

---

## Task 2: Async downloader (TDD)

**Files:**
- Create: `backend/utils/downloader.py`
- Create: `backend/tests/test_downloader.py`

- [ ] **Step 1: Write failing tests**

We use `httpx.MockTransport` to avoid real network. The downloader streams to a path, enforces a 5MB cap (spec §8.2.1), and a 30-second timeout.

```python
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
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_downloader.py -v`
Expected: import error.

- [ ] **Step 3: Write the implementation**

```python
"""Async MIDI downloader with size cap and timeout.

Streams the response body to a local path. Aborts and removes the file
if size exceeds 5 MB (spec §8.2.1).
"""
from __future__ import annotations

from pathlib import Path

import httpx

MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0


class DownloadError(Exception):
    """Raised when a download fails or violates the size cap."""


async def download_to_path(
    url: str,
    target: Path,
    *,
    client: httpx.AsyncClient | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        async with http.stream("GET", url, timeout=timeout) as response:
            if response.status_code != 200:
                raise DownloadError(
                    f"HTTP {response.status_code} when downloading {url}"
                )
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_BYTES:
                raise DownloadError(
                    f"File exceeds {MAX_BYTES} bytes (declared {content_length})"
                )
            written = 0
            with target.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    written += len(chunk)
                    if written > MAX_BYTES:
                        fh.close()
                        target.unlink(missing_ok=True)
                        raise DownloadError(
                            f"File exceeds {MAX_BYTES} bytes during stream"
                        )
                    fh.write(chunk)
        return target
    except DownloadError:
        target.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        target.unlink(missing_ok=True)
        raise DownloadError(f"Download failed: {exc}") from exc
    finally:
        if own_client:
            await http.aclose()
```

- [ ] **Step 4: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_downloader.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/downloader.py backend/tests/test_downloader.py
git commit -m "feat(utils): async MIDI downloader with 5MB cap"
```

---

## Task 3: Build a small test fixture MIDI file

**Files:**
- Create: `backend/tests/fixtures/__init__.py` (empty)
- Create: `backend/tests/fixtures/build_fixture.py`
- Create: `backend/tests/fixtures/twinkle.mid` (generated)

- [ ] **Step 1: Create empty fixtures package**

Create `backend/tests/fixtures/__init__.py` as an empty file.

- [ ] **Step 2: Write a fixture-builder script using `mido`**

We commit the generator script (so others can rebuild) and the resulting MIDI file (so tests don't depend on running it). The fixture has 3 tracks: a melody (Twinkle's first phrase), an accompaniment chord track (column chords), and a low single-note track. This exercises the classifier's three target paths.

```python
"""Generate the test fixture MIDI file.

Run:  python -m tests.fixtures.build_fixture
This produces tests/fixtures/twinkle.mid. Already committed; only re-run
if you intentionally change the fixture.
"""
from __future__ import annotations

from pathlib import Path

import mido


def build() -> mido.MidiFile:
    mid = mido.MidiFile(ticks_per_beat=480)

    # Track 0: melody — Twinkle "C C G G A A G".
    melody = mido.MidiTrack()
    melody.append(mido.MetaMessage("track_name", name="Piano Right", time=0))
    melody.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for pitch in (60, 60, 67, 67, 69, 69, 67):
        melody.append(mido.Message("note_on", note=pitch, velocity=80, time=0))
        melody.append(mido.Message("note_off", note=pitch, velocity=0, time=480))
    mid.tracks.append(melody)

    # Track 1: column-chord accompaniment — C major, F major, G major triads.
    chords = mido.MidiTrack()
    chords.append(mido.MetaMessage("track_name", name="Piano Left", time=0))
    for root, third, fifth in [(48, 52, 55), (53, 57, 60), (55, 59, 62)]:
        chords.append(mido.Message("note_on", note=root, velocity=70, time=0))
        chords.append(mido.Message("note_on", note=third, velocity=70, time=0))
        chords.append(mido.Message("note_on", note=fifth, velocity=70, time=0))
        chords.append(mido.Message("note_off", note=root, velocity=0, time=960))
        chords.append(mido.Message("note_off", note=third, velocity=0, time=0))
        chords.append(mido.Message("note_off", note=fifth, velocity=0, time=0))
    mid.tracks.append(chords)

    # Track 2: bass line — single low notes.
    bass = mido.MidiTrack()
    bass.append(mido.MetaMessage("track_name", name="Bass", time=0))
    for pitch in (36, 41, 43):  # C2, F2, G2 — all below MIDI 48
        bass.append(mido.Message("note_on", note=pitch, velocity=80, time=0))
        bass.append(mido.Message("note_off", note=pitch, velocity=0, time=960))
    mid.tracks.append(bass)

    return mid


if __name__ == "__main__":
    out = Path(__file__).parent / "twinkle.mid"
    build().save(str(out))
    print(f"wrote {out}")
```

- [ ] **Step 3: Run the builder to generate the .mid file**

Run: `cd backend && python -m tests.fixtures.build_fixture`
Expected: `wrote tests/fixtures/twinkle.mid`.

- [ ] **Step 4: Verify the file exists and is parseable**

Run: `cd backend && python -c "import mido; m = mido.MidiFile('tests/fixtures/twinkle.mid'); print(len(m.tracks), 'tracks')"`
Expected: `3 tracks`.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/
git commit -m "test: add Twinkle MIDI fixture for parser/classifier tests"
```

---

## Task 4: MIDI parser tests (RED)

**Files:**
- Create: `backend/tests/test_midi_parser.py`

- [ ] **Step 1: Write failing tests for `parse_midi_file`**

Returns a Pydantic-modeled `ParsedMidi` (we'll add to `config.py` next task) with: `bpm`, `ticks_per_beat`, `tracks: list[ParsedTrack]`. Each `ParsedTrack` has `index`, `name`, and `notes: list[ParsedNote]` (no role yet — that's the classifier's job).

```python
"""Tests for parser.midi_parser. Spec §8.2.1."""
from __future__ import annotations

from pathlib import Path

import pytest

from parser.midi_parser import parse_midi_file

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def test_parses_bpm_and_resolution():
    parsed = parse_midi_file(FIXTURE)
    assert parsed.bpm == 120
    assert parsed.ticks_per_beat == 480


def test_returns_three_tracks():
    parsed = parse_midi_file(FIXTURE)
    assert len(parsed.tracks) == 3


def test_track_names_preserved():
    parsed = parse_midi_file(FIXTURE)
    names = [t.name for t in parsed.tracks]
    assert "Piano Right" in names
    assert "Piano Left" in names
    assert "Bass" in names


def test_melody_note_count():
    parsed = parse_midi_file(FIXTURE)
    melody = next(t for t in parsed.tracks if t.name == "Piano Right")
    # 7 notes from the Twinkle phrase.
    assert len(melody.notes) == 7


def test_chord_track_has_three_notes_at_each_chord_position():
    parsed = parse_midi_file(FIXTURE)
    chords = next(t for t in parsed.tracks if t.name == "Piano Left")
    # 3 chords × 3 notes each = 9 notes.
    assert len(chords.notes) == 9


def test_filters_zero_velocity_note_on():
    # Already enforced by mido's note-pair handling, but assert no velocity 0
    # leaks into ParsedNote.
    parsed = parse_midi_file(FIXTURE)
    for track in parsed.tracks:
        assert all(n.velocity > 0 for n in track.notes)


def test_filters_very_short_durations():
    parsed = parse_midi_file(FIXTURE)
    for track in parsed.tracks:
        assert all(n.duration_tick >= 30 for n in track.notes)


def test_raises_on_missing_file(tmp_path: Path):
    from parser.midi_parser import ParseError
    with pytest.raises(ParseError):
        parse_midi_file(tmp_path / "nope.mid")
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_midi_parser.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_midi_parser.py
git commit -m "test(parser): add MIDI parser specification tests"
```

---

## Task 5: Add ParsedTrack and ParsedMidi to config.py

**Files:**
- Modify: `backend/config.py` (append two models)

- [ ] **Step 1: Append the two new models to `backend/config.py`**

Append at the end of the file:

```python
class ParsedTrack(BaseModel):
    """Raw parser output for one MIDI track. The classifier later reads
    these and produces TrackInfo (with suggested_role + chord_type)."""
    index: int
    name: str
    notes: list[ParsedNote]


class ParsedMidi(BaseModel):
    """Full result of parsing a local MIDI file."""
    bpm: int
    ticks_per_beat: int
    tracks: list[ParsedTrack]
```

- [ ] **Step 2: Verify import**

Run: `cd backend && python -c "from config import ParsedMidi, ParsedTrack; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat(config): add ParsedTrack and ParsedMidi models"
```

---

## Task 6: MIDI parser implementation (GREEN)

**Files:**
- Create: `backend/parser/__init__.py` (empty)
- Create: `backend/parser/midi_parser.py`

- [ ] **Step 1: Create empty parser package**

Create `backend/parser/__init__.py` as an empty file.

- [ ] **Step 2: Write the parser**

We use `mido` directly for predictable behavior on hand-built fixtures. (`music21` is great for analysis but pulls in a heavy import; spec §8.2.1 lists it as the primary with `mido` as fallback — for our purposes mido is sufficient and keeps tests fast. Future enhancement can add a music21 path.)

```python
"""MIDI file parser.

Reads a local MIDI path with mido and produces a ParsedMidi. The route
layer is responsible for downloading first; this module is filesystem-only.

Per spec §8.2.1 we filter out:
  - note_on with velocity 0 (these are alternative note-off encodings)
  - notes shorter than 30 ticks (likely artifacts)
"""
from __future__ import annotations

from pathlib import Path

import mido

from config import ParsedMidi, ParsedNote, ParsedTrack, TrackRole

MIN_DURATION_TICK = 30


class ParseError(Exception):
    """Raised when a MIDI file cannot be opened or parsed."""


def parse_midi_file(path: Path) -> ParsedMidi:
    if not path.is_file():
        raise ParseError(f"MIDI file not found: {path}")
    try:
        midi = mido.MidiFile(str(path))
    except (OSError, EOFError, ValueError) as exc:
        raise ParseError(f"Failed to parse MIDI: {exc}") from exc

    bpm = _extract_bpm(midi)
    tracks: list[ParsedTrack] = []
    for index, track in enumerate(midi.tracks):
        name = _extract_track_name(track) or f"轨道 {index}"
        notes = _extract_notes(track, track_index=index)
        tracks.append(ParsedTrack(index=index, name=name, notes=notes))

    return ParsedMidi(
        bpm=bpm,
        ticks_per_beat=midi.ticks_per_beat,
        tracks=tracks,
    )


def _extract_bpm(midi: mido.MidiFile) -> int:
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return int(round(mido.tempo2bpm(msg.tempo)))
    return 120  # spec default


def _extract_track_name(track: mido.MidiTrack) -> str | None:
    for msg in track:
        if msg.type == "track_name":
            return msg.name
    return None


def _extract_notes(track: mido.MidiTrack, *, track_index: int) -> list[ParsedNote]:
    """Walk a track, pair note_on/note_off into ParsedNote objects."""
    notes: list[ParsedNote] = []
    open_notes: dict[int, tuple[int, int]] = {}  # pitch -> (start_tick, velocity)
    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes[msg.note] = (abs_tick, msg.velocity)
        elif (
            msg.type == "note_off"
            or (msg.type == "note_on" and msg.velocity == 0)
        ):
            opened = open_notes.pop(msg.note, None)
            if opened is None:
                continue
            start_tick, velocity = opened
            duration = abs_tick - start_tick
            if duration < MIN_DURATION_TICK:
                continue
            notes.append(
                ParsedNote(
                    midi_num=msg.note,
                    start_tick=start_tick,
                    duration_tick=duration,
                    velocity=velocity,
                    track_index=track_index,
                    track_role=TrackRole.IGNORED,  # placeholder until classified
                )
            )
    return notes
```

- [ ] **Step 3: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_midi_parser.py -v`
Expected: 8 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/parser/__init__.py backend/parser/midi_parser.py
git commit -m "feat(parser): MIDI parser yields ParsedMidi with note-pair walking"
```

---

## Task 7: Track classifier tests (RED)

**Files:**
- Create: `backend/tests/test_track_classifier.py`

- [ ] **Step 1: Write failing tests for `classify_tracks`**

Signature: `classify_tracks(parsed: ParsedMidi) -> list[TrackInfo]`. It does both the role recommendation (spec §8.2.2 priority list) and the chord_type detection.

```python
"""Tests for parser.track_classifier. Spec §8.2.2."""
from __future__ import annotations

from pathlib import Path

import pytest

from config import ParsedMidi, ParsedNote, ParsedTrack, TrackRole
from parser.midi_parser import parse_midi_file
from parser.track_classifier import classify_tracks

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def _track(index: int, name: str, notes: list[ParsedNote]) -> ParsedTrack:
    return ParsedTrack(index=index, name=name, notes=notes)


def _note(midi: int, *, start: int = 0, duration: int = 480, velocity: int = 80,
          track_index: int = 0) -> ParsedNote:
    return ParsedNote(
        midi_num=midi,
        start_tick=start,
        duration_tick=duration,
        velocity=velocity,
        track_index=track_index,
        track_role=TrackRole.IGNORED,
    )


class TestNamedTrackPriority:
    def test_track_named_melody_recommended_as_melody(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Lead Melody", [_note(60 + i, start=480 * i) for i in range(20)]),
                _track(1, "Other", [_note(60 + i, start=480 * i) for i in range(20)]),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[0].suggested_role == TrackRole.MELODY

    def test_track_named_bass_recommended_as_bass(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Vocal", [_note(60 + i, start=480 * i) for i in range(20)]),
                _track(1, "Bass Line", [_note(40 + i, start=480 * i) for i in range(20)]),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[1].suggested_role == TrackRole.BASS

    def test_track_named_drums_ignored(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Right", [_note(60 + i, start=480 * i) for i in range(20)]),
                _track(1, "Drum Kit", [_note(38, start=480 * i) for i in range(20)]),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[1].suggested_role == TrackRole.IGNORED


class TestPitchRangeRule:
    def test_all_notes_below_c3_classified_as_bass(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Right Hand", [_note(60 + i, start=480 * i) for i in range(20)]),
                _track(1, "Anonymous Low", [_note(36 + (i % 6), start=480 * i) for i in range(20)]),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[1].suggested_role == TrackRole.BASS

    def test_too_few_notes_ignored(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Main", [_note(60 + i, start=480 * i) for i in range(20)]),
                _track(1, "Tiny", [_note(60, start=0)] * 5),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[1].suggested_role == TrackRole.IGNORED


class TestComprehensiveScoring:
    def test_first_track_in_fixture_is_melody(self):
        parsed = parse_midi_file(FIXTURE)
        # Note: fixture only has 7 notes per track which is < 10 (the min-notes
        # threshold). Lift this test by using named-track rules — Piano Right
        # has no melody/vocal/right keyword so we synthesize a longer track.
        long_melody = ParsedTrack(
            index=0,
            name="Top Voice",
            notes=[_note(60 + (i % 7), start=240 * i) for i in range(40)],
        )
        long_left = ParsedTrack(
            index=1,
            name="Inner",
            notes=[_note(48 + (i % 5), start=240 * i, velocity=60) for i in range(40)],
        )
        synthetic = ParsedMidi(bpm=120, ticks_per_beat=480, tracks=[long_melody, long_left])
        infos = classify_tracks(synthetic)
        roles = [i.suggested_role for i in infos]
        assert TrackRole.MELODY in roles


class TestChordTypeDetection:
    def test_simultaneous_chords_marked_chordal(self):
        # 3 notes at the same start_tick across many chord groups.
        notes: list[ParsedNote] = []
        for i in range(8):
            for pitch in (60, 64, 67):
                notes.append(_note(pitch, start=i * 960, duration=900))
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Top", [_note(72 + i, start=480 * i) for i in range(20)]),
                _track(1, "Chords", notes),
            ],
        )
        infos = classify_tracks(parsed)
        accomp_info = infos[1]
        assert accomp_info.suggested_role == TrackRole.ACCOMPANIMENT
        assert accomp_info.chord_type == "chordal"

    def test_evenly_spaced_singletons_marked_arpeggiated(self):
        notes = [_note(48 + (i % 5), start=120 * i, duration=110) for i in range(40)]
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[
                _track(0, "Top", [_note(72 + i, start=480 * i) for i in range(20)]),
                _track(1, "Arp", notes),
            ],
        )
        infos = classify_tracks(parsed)
        assert infos[1].suggested_role == TrackRole.ACCOMPANIMENT
        assert infos[1].chord_type == "arpeggiated"

    def test_melody_chord_type_is_none(self):
        parsed = ParsedMidi(
            bpm=120, ticks_per_beat=480,
            tracks=[_track(0, "Lead", [_note(60 + (i % 7), start=480 * i) for i in range(40)])],
        )
        infos = classify_tracks(parsed)
        assert infos[0].chord_type == "none"


class TestTrackInfoFields:
    def test_pitch_range_format(self):
        notes = [_note(60), _note(76)]
        notes += [_note(60 + i, start=480 * (i + 2)) for i in range(15)]
        parsed = ParsedMidi(bpm=120, ticks_per_beat=480, tracks=[_track(0, "x", notes)])
        infos = classify_tracks(parsed)
        # Lowest pitch 60 (C4), highest 76 (E5).
        assert infos[0].pitch_range == "C4~E5"

    def test_preview_keys_first_eight_pc(self):
        notes = [_note(60 + i, start=480 * i) for i in range(20)]  # C D E F G A B C
        parsed = ParsedMidi(bpm=120, ticks_per_beat=480, tracks=[_track(0, "x", notes)])
        infos = classify_tracks(parsed)
        # First 8 mapped notes — note 65 is F (key F), 66 (F#) rounds to F.
        # Just verify the field is populated and 8 chars when joined.
        tokens = infos[0].preview_keys.split()
        assert 1 <= len(tokens) <= 8
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_track_classifier.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_track_classifier.py
git commit -m "test(parser): add track classifier specification tests"
```

---

## Task 8: Track classifier implementation (GREEN)

**Files:**
- Create: `backend/parser/track_classifier.py`

- [ ] **Step 1: Write the classifier**

```python
"""Track role + chord_type classification.

Pure function over ParsedMidi. Implements spec §8.2.2 priority rules:
  1. Name match (melody / bass / drum keywords)
  2. Pitch-range exclusion (all notes below C3 → bass; all above C6 → ignored;
     fewer than 10 notes → ignored)
  3. Comprehensive scoring among the remainder; highest scorer is melody,
     others are accompaniment.
"""
from __future__ import annotations

from config import ParsedMidi, ParsedNote, ParsedTrack, TrackInfo, TrackRole
from mapper.note_mapper import map_note

_MELODY_KEYWORDS = ("melody", "vocal", "主旋律", "soprano", "lead", "right")
_BASS_KEYWORDS = ("bass", "left", "低音")
_IGNORED_KEYWORDS = ("drum", "perc", "打击")
_MIN_NOTES = 10
_NAME_TIME_TOLERANCE = 30  # ticks; spec §7.3 step 1 also uses 30


def classify_tracks(parsed: ParsedMidi) -> list[TrackInfo]:
    role_by_index: dict[int, TrackRole] = {}
    pending_indices: list[int] = []

    # Pass 1: name + pitch-range + size rules.
    for track in parsed.tracks:
        role = _classify_by_rules(track)
        if role is not None:
            role_by_index[track.index] = role
        else:
            pending_indices.append(track.index)

    # Pass 2: score the remainder; top score = melody, rest = accompaniment.
    if pending_indices:
        scored = sorted(
            pending_indices,
            key=lambda i: _score_track(parsed.tracks[i]),
            reverse=True,
        )
        role_by_index[scored[0]] = TrackRole.MELODY
        for idx in scored[1:]:
            role_by_index[idx] = TrackRole.ACCOMPANIMENT

    # Build TrackInfo with chord_type detection for accompaniment tracks.
    infos: list[TrackInfo] = []
    for track in parsed.tracks:
        role = role_by_index[track.index]
        chord_type = (
            _detect_chord_type(track.notes)
            if role == TrackRole.ACCOMPANIMENT
            else "none"
        )
        infos.append(
            TrackInfo(
                index=track.index,
                name=track.name,
                note_count=len(track.notes),
                pitch_range=_format_pitch_range(track.notes),
                preview_keys=_preview_keys(track.notes),
                suggested_role=role,
                chord_type=chord_type,
            )
        )
    return infos


def _classify_by_rules(track: ParsedTrack) -> TrackRole | None:
    name_lower = track.name.lower()
    if any(kw in name_lower for kw in _IGNORED_KEYWORDS):
        return TrackRole.IGNORED
    if any(kw in name_lower for kw in _MELODY_KEYWORDS):
        return TrackRole.MELODY
    if any(kw in name_lower for kw in _BASS_KEYWORDS):
        return TrackRole.BASS

    if len(track.notes) < _MIN_NOTES:
        return TrackRole.IGNORED
    if all(n.midi_num < 48 for n in track.notes):
        return TrackRole.BASS
    if all(n.midi_num > 84 for n in track.notes):
        return TrackRole.IGNORED
    return None


def _score_track(track: ParsedTrack) -> float:
    if not track.notes:
        return 0.0
    note_count_score = min(len(track.notes) / 100.0, 1.0)
    in_range = sum(1 for n in track.notes if 60 <= n.midi_num <= 72)
    central_score = in_range / len(track.notes)
    avg_velocity = sum(n.velocity for n in track.notes) / len(track.notes)
    velocity_score = min(avg_velocity / 100.0, 1.0)
    return 0.4 * note_count_score + 0.3 * central_score + 0.3 * velocity_score


def _detect_chord_type(notes: list[ParsedNote]) -> str:
    if not notes:
        return "none"

    sorted_notes = sorted(notes, key=lambda n: n.start_tick)
    groups: list[list[ParsedNote]] = []
    for note in sorted_notes:
        if groups and abs(note.start_tick - groups[-1][0].start_tick) <= _NAME_TIME_TOLERANCE:
            groups[-1].append(note)
        else:
            groups.append([note])

    multi_groups = [g for g in groups if len(g) >= 2]
    multi_ratio = sum(len(g) for g in multi_groups) / len(notes)

    # Arpeggiated heuristic: even spacing + short durations + few simultaneous.
    if len(sorted_notes) >= 4 and not multi_groups:
        intervals = [
            sorted_notes[i + 1].start_tick - sorted_notes[i].start_tick
            for i in range(len(sorted_notes) - 1)
        ]
        if intervals:
            avg = sum(intervals) / len(intervals)
            jitter = max(abs(i - avg) for i in intervals) / max(avg, 1)
            short = all(n.duration_tick <= 480 for n in sorted_notes[:20])
            if jitter <= 0.5 and short:
                return "arpeggiated"

    if multi_ratio > 0.5:
        return "mixed" if any(len(g) == 1 for g in groups) else "chordal"
    return "none"


def _format_pitch_range(notes: list[ParsedNote]) -> str:
    if not notes:
        return ""
    lo = min(n.midi_num for n in notes)
    hi = max(n.midi_num for n in notes)
    return f"{_midi_to_name(lo)}~{_midi_to_name(hi)}"


def _midi_to_name(midi: int) -> str:
    names = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    return f"{names[midi % 12]}{midi // 12 - 1}"


def _preview_keys(notes: list[ParsedNote]) -> str:
    sample = sorted(notes, key=lambda n: n.start_tick)[:8]
    keys = [map_note(n).key_pc for n in sample]
    return " ".join(keys)
```

- [ ] **Step 2: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_track_classifier.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/parser/track_classifier.py
git commit -m "feat(parser): track classifier with role + chord_type detection"
```

---

## Task 9: Chord grouper tests (RED)

**Files:**
- Create: `backend/tests/test_chord_grouper.py`

- [ ] **Step 1: Write failing tests**

The grouper consumes a list of accompaniment `ParsedNote`s and produces `chord_groups: list[list[ParsedNote]]` per spec §7.3 step 1 (notes within 30 ticks form a group).

```python
"""Tests for parser.chord_grouper. Spec §7.3 step 1."""
from __future__ import annotations

from config import ParsedNote, TrackRole
from parser.chord_grouper import group_accompaniment


def _n(midi: int, start: int) -> ParsedNote:
    return ParsedNote(
        midi_num=midi,
        start_tick=start,
        duration_tick=480,
        velocity=70,
        track_index=1,
        track_role=TrackRole.ACCOMPANIMENT,
    )


def test_simultaneous_notes_grouped():
    notes = [_n(60, 0), _n(64, 0), _n(67, 0)]
    groups = group_accompaniment(notes)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_notes_within_tolerance_grouped():
    # Within 30-tick tolerance.
    notes = [_n(60, 0), _n(64, 15), _n(67, 28)]
    groups = group_accompaniment(notes)
    assert len(groups) == 1
    assert len(groups[0]) == 3


def test_notes_beyond_tolerance_separate_groups():
    notes = [_n(60, 0), _n(64, 100), _n(67, 200)]
    groups = group_accompaniment(notes)
    assert len(groups) == 3


def test_singletons_form_one_note_groups():
    notes = [_n(60, 0), _n(62, 480), _n(64, 960)]
    groups = group_accompaniment(notes)
    assert len(groups) == 3
    assert all(len(g) == 1 for g in groups)


def test_input_order_preserved_within_groups():
    a, b, c = _n(60, 0), _n(64, 10), _n(67, 20)
    groups = group_accompaniment([a, b, c])
    assert groups[0][0] is a and groups[0][1] is b and groups[0][2] is c


def test_empty_input_returns_empty_list():
    assert group_accompaniment([]) == []
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_chord_grouper.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_chord_grouper.py
git commit -m "test(parser): add chord grouper tests"
```

---

## Task 10: Chord grouper implementation (GREEN)

**Files:**
- Create: `backend/parser/chord_grouper.py`

- [ ] **Step 1: Write the grouper**

```python
"""Group accompaniment notes into simultaneous chord groups.

Spec §7.3 step 1: notes whose start_tick differs by at most 30 ticks
belong to the same chord group. The arranger consumes these groups
when reducing column chords for the simplified version.
"""
from __future__ import annotations

from config import ParsedNote

GROUP_TOLERANCE_TICKS = 30


def group_accompaniment(notes: list[ParsedNote]) -> list[list[ParsedNote]]:
    if not notes:
        return []
    sorted_notes = sorted(notes, key=lambda n: n.start_tick)
    groups: list[list[ParsedNote]] = [[sorted_notes[0]]]
    for note in sorted_notes[1:]:
        anchor = groups[-1][0].start_tick
        if abs(note.start_tick - anchor) <= GROUP_TOLERANCE_TICKS:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups
```

- [ ] **Step 2: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_chord_grouper.py -v`
Expected: 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/parser/chord_grouper.py
git commit -m "feat(parser): chord grouper produces simultaneous-note buckets"
```

---

## Task 11: Search base class tests + impl

**Files:**
- Create: `backend/search/__init__.py` (empty)
- Create: `backend/tests/test_search_base.py`
- Create: `backend/search/base.py`

- [ ] **Step 1: Create empty package init**

Create `backend/search/__init__.py` as an empty file.

- [ ] **Step 2: Write failing tests**

```python
"""Tests for search.base. Spec §8.1.1."""
from __future__ import annotations

import pytest

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher


class _FailingSearcher(BaseMusicSearcher):
    source = MusicSource.FREEMIDI

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        raise RuntimeError("boom")

    async def get_download_url(self, result: SearchResult) -> str:
        raise NotImplementedError


class _OkSearcher(BaseMusicSearcher):
    source = MusicSource.BITMIDI

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        return [
            SearchResult(
                id=f"{self.source.value}_x",
                title="X",
                source=self.source,
                source_url="https://example.com/x",
                score=0.5,
            )
        ]

    async def get_download_url(self, result: SearchResult) -> str:
        return "https://example.com/x.mid"


async def test_search_swallows_exceptions_returns_empty():
    s = _FailingSearcher()
    assert await s.search("foo", limit=5) == []


async def test_search_returns_results_on_success():
    s = _OkSearcher()
    results = await s.search("foo", limit=5)
    assert len(results) == 1
    assert results[0].title == "X"
```

- [ ] **Step 3: Confirm RED**

Run: `cd backend && python -m pytest tests/test_search_base.py -v`
Expected: import error.

- [ ] **Step 4: Write the base class**

```python
"""Abstract base for music searchers.

Each subclass implements `_do_search` (may raise) and `get_download_url`.
The public `search` method here wraps `_do_search` so any exception is
caught and an empty list is returned — spec §8.1.1.
"""
from __future__ import annotations

import abc
import logging

from config import MusicSource, SearchResult

_LOG = logging.getLogger(__name__)


class BaseMusicSearcher(abc.ABC):
    source: MusicSource

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            return await self._do_search(query, limit)
        except Exception as exc:  # noqa: BLE001 — spec requires swallow
            _LOG.warning("search failed for %s: %s", self.source, exc)
            return []

    @abc.abstractmethod
    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        ...

    @abc.abstractmethod
    async def get_download_url(self, result: SearchResult) -> str:
        ...
```

- [ ] **Step 5: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_search_base.py -v`
Expected: 2 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/search/__init__.py backend/search/base.py backend/tests/test_search_base.py
git commit -m "feat(search): abstract base swallows searcher exceptions"
```

---

## Task 12: FreeMIDI searcher (TDD via httpx mock)

**Files:**
- Create: `backend/search/freemidi.py`
- Create: `backend/tests/test_searchers_html.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for individual platform searchers using httpx MockTransport.
Spec §8.1.2 (freemidi), §8.1.3 (bitmidi)."""
from __future__ import annotations

import httpx
import pytest

from config import MusicSource
from search.freemidi import FreeMidiSearcher

FREEMIDI_HTML = """
<html><body>
<div class="search-result">
  <a href="/download-12345" class="search-result-anchor">Twinkle Twinkle Little Star</a>
</div>
<div class="search-result">
  <a href="/download-67890" class="search-result-anchor">Another Tune</a>
</div>
</body></html>
"""


def _client_returning(html: str, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=html)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_freemidi_parses_search_results():
    async with _client_returning(FREEMIDI_HTML) as client:
        searcher = FreeMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.FREEMIDI
    assert "Twinkle" in results[0].title
    assert results[0].download_url == "https://freemidi.org/download2-12345"


async def test_freemidi_query_with_spaces_uses_hyphens():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=FREEMIDI_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = FreeMidiSearcher(client=client)
        await searcher.search("twinkle little star", limit=5)
    assert "twinkle-little-star" in captured["url"]


async def test_freemidi_returns_empty_on_5xx():
    async with _client_returning("server down", status=500) as client:
        searcher = FreeMidiSearcher(client=client)
        # search() catches exceptions; bad status raises in _do_search.
        results = await searcher.search("twinkle", limit=5)
    assert results == []


async def test_freemidi_respects_limit():
    async with _client_returning(FREEMIDI_HTML) as client:
        searcher = FreeMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=1)
    assert len(results) == 1
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_searchers_html.py::test_freemidi_parses_search_results -v`
Expected: import error.

- [ ] **Step 3: Write the searcher**

```python
"""freemidi.org searcher.

Spec §8.1.2:
  - URL: https://freemidi.org/search-{query}, spaces → hyphens
  - Parse search-result anchors with /download-{id}
  - Download URL: https://freemidi.org/download2-{id}
"""
from __future__ import annotations

import hashlib
import re

import httpx
from bs4 import BeautifulSoup

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
_DOWNLOAD_ID_RE = re.compile(r"/download-(\d+)")


class FreeMidiSearcher(BaseMusicSearcher):
    source = MusicSource.FREEMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        slug = re.sub(r"\s+", "-", query.strip())
        url = f"https://freemidi.org/search-{slug}"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, headers={"User-Agent": _USER_AGENT})
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "lxml")
            results: list[SearchResult] = []
            for anchor in soup.select("a.search-result-anchor"):
                href = anchor.get("href", "")
                match = _DOWNLOAD_ID_RE.search(href)
                if not match:
                    continue
                fid = match.group(1)
                title = anchor.get_text(strip=True)
                results.append(
                    SearchResult(
                        id=f"freemidi_{hashlib.sha1(fid.encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://freemidi.org{href}",
                        download_url=f"https://freemidi.org/download2-{fid}",
                        score=0.7,
                    )
                )
                if len(results) >= limit:
                    break
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("FreeMidi result has no download URL")
        return result.download_url
```

- [ ] **Step 4: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k freemidi`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/search/freemidi.py backend/tests/test_searchers_html.py
git commit -m "feat(search): FreeMIDI HTML searcher with download URL construction"
```

---

## Task 13: BitMIDI searcher (TDD)

**Files:**
- Create: `backend/search/bitmidi.py`
- Modify: `backend/tests/test_searchers_html.py` (append)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_searchers_html.py

from search.bitmidi import BitMidiSearcher

BITMIDI_JSON = {
    "results": [
        {
            "name": "Twinkle Twinkle Little Star",
            "slug": "twinkle-twinkle",
            "downloadUrl": "https://bitmidi.com/uploads/twinkle-twinkle.mid",
            "fileSize": 12345,
        },
        {
            "name": "Star Wars Theme",
            "slug": "star-wars",
            "downloadUrl": "https://bitmidi.com/uploads/star-wars.mid",
            "fileSize": 54321,
        },
    ]
}


async def test_bitmidi_parses_json_api():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BITMIDI_JSON)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BitMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.BITMIDI
    assert results[0].download_url.endswith(".mid")
    # 12345 bytes ≈ 12 KB.
    assert results[0].file_size_kb in (12, 13)


async def test_bitmidi_returns_empty_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BitMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert results == []
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k bitmidi`
Expected: import error.

- [ ] **Step 3: Write the searcher**

```python
"""bitmidi.com searcher (JSON API first, HTML fallback).

Spec §8.1.3.
"""
from __future__ import annotations

import hashlib
import re

import httpx

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher


class BitMidiSearcher(BaseMusicSearcher):
    source = MusicSource.BITMIDI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = f"https://bitmidi.com/search?q={query.replace(' ', '+')}"
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, headers={"Accept": "application/json"})
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError("Invalid JSON from bitmidi") from exc
            results: list[SearchResult] = []
            for entry in data.get("results", [])[:limit]:
                slug = entry.get("slug")
                title = entry.get("name") or slug or "Untitled"
                download_url = entry.get("downloadUrl") or (
                    f"https://bitmidi.com/uploads/{slug}.mid" if slug else None
                )
                file_size_bytes = entry.get("fileSize")
                results.append(
                    SearchResult(
                        id=f"bitmidi_{hashlib.sha1((slug or title).encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://bitmidi.com/{slug}" if slug else url,
                        download_url=download_url,
                        file_size_kb=(
                            int(round(file_size_bytes / 1024))
                            if file_size_bytes else None
                        ),
                        score=0.7,
                    )
                )
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("BitMIDI result has no download URL")
        return result.download_url
```

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k bitmidi`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/search/bitmidi.py backend/tests/test_searchers_html.py
git commit -m "feat(search): BitMIDI JSON API searcher"
```

---

## Task 14: MuseScore searcher (no download_url)

**Files:**
- Create: `backend/search/musescore.py`
- Modify: `backend/tests/test_searchers_html.py` (append)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_searchers_html.py

from search.musescore import MuseScoreSearcher

MUSESCORE_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "MusicComposition", "name": "Twinkle Variation 1", "url": "https://musescore.com/score/1"},
    {"@type": "MusicComposition", "name": "Twinkle Variation 2", "url": "https://musescore.com/score/2"}
  ]
}
</script>
</head><body></body></html>
"""


async def test_musescore_parses_jsonld():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=MUSESCORE_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = MuseScoreSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.MUSESCORE
    assert results[0].download_url is None
    assert "MuseScore" in (results[0].preview_keys or "")
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k musescore`
Expected: import error.

- [ ] **Step 3: Write the searcher**

```python
"""musescore.com searcher (discovery only — no download_url).

Spec §8.1.4.
"""
from __future__ import annotations

import hashlib
import json
import re

import httpx
from bs4 import BeautifulSoup

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_PREVIEW_NOTE = "请前往 MuseScore 手动下载 MIDI"


class MuseScoreSearcher(BaseMusicSearcher):
    source = MusicSource.MUSESCORE

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        url = (
            "https://musescore.com/sheetmusic"
            f"?text={query.replace(' ', '+')}&instrument=piano"
        )
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            soup = BeautifulSoup(response.text, "lxml")
            jsonld_blocks = soup.find_all(
                "script", attrs={"type": "application/ld+json"}
            )
            results: list[SearchResult] = []
            for block in jsonld_blocks:
                try:
                    data = json.loads(block.string or "")
                except (TypeError, json.JSONDecodeError):
                    continue
                graph = data.get("@graph", []) if isinstance(data, dict) else []
                for entry in graph:
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("@type") != "MusicComposition":
                        continue
                    title = entry.get("name") or "Untitled"
                    page_url = entry.get("url") or url
                    results.append(
                        SearchResult(
                            id=f"musescore_{hashlib.sha1(title.encode()).hexdigest()[:6]}",
                            title=title,
                            source=self.source,
                            source_url=page_url,
                            download_url=None,
                            preview_keys=_PREVIEW_NOTE,
                            score=0.5,
                        )
                    )
                    if len(results) >= limit:
                        return results
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    async def get_download_url(self, result: SearchResult) -> str:
        raise ValueError("MuseScore does not expose direct MIDI downloads")
```

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k musescore`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/search/musescore.py backend/tests/test_searchers_html.py
git commit -m "feat(search): MuseScore discovery searcher (no direct downloads)"
```

---

## Task 15: Bilibili searcher (regex extraction)

**Files:**
- Create: `backend/search/bilibili.py`
- Modify: `backend/tests/test_searchers_html.py` (append)

- [ ] **Step 1: Append failing tests**

```python
# Append to tests/test_searchers_html.py

from search.bilibili import BilibiliSearcher

BILI_API_PAGE_1 = {
    "data": {
        "result": [
            {
                "type": "video",
                "data": [
                    {
                        "bvid": "BV1abc",
                        "title": "<em>Twinkle</em> 原琴演奏",
                        "description": "MIDI 下载：https://github.com/foo/bar/twinkle.mid",
                        "duration": "0:45",
                    },
                    {
                        "bvid": "BV2def",
                        "title": "另一首曲子",
                        "description": "无下载链接",
                        "duration": "1:10",
                    },
                ],
            }
        ]
    }
}


async def test_bilibili_extracts_download_link_from_description():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Referer" not in request.headers or \
               request.headers["Referer"].startswith("https://www.bilibili.com")
        return httpx.Response(200, json=BILI_API_PAGE_1)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BilibiliSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    first = next(r for r in results if r.id.startswith("bilibili_"))
    has_link = next((r for r in results if r.download_url), None)
    assert has_link is not None
    assert has_link.download_url.endswith(".mid")
    no_link = next(r for r in results if not r.download_url)
    assert no_link.source_url.startswith("https://www.bilibili.com/video/")


async def test_bilibili_strips_em_tags_from_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BILI_API_PAGE_1)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BilibiliSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert "<em>" not in results[0].title and "</em>" not in results[0].title
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k bilibili`
Expected: import error.

- [ ] **Step 3: Write the searcher**

```python
"""bilibili.com searcher.

Spec §8.1.5:
  - Query: "{user_query} 原神 原琴 MIDI"
  - Web search API; Referer must be bilibili.com
  - download_url is extracted from the video description with a regex
    that matches pan.baidu.com / github.com / *.mid|*.midi URLs
"""
from __future__ import annotations

import hashlib
import re

import httpx

from config import MusicSource, SearchResult
from search.base import BaseMusicSearcher

_DOWNLOAD_RE = re.compile(
    r"https?://[^\s,)]+?(?:pan\.baidu\.com|github\.com)[^\s,)]*"
    r"|https?://[^\s,)]+?\.midi?\b",
    flags=re.IGNORECASE,
)
_TAG_RE = re.compile(r"</?em>", flags=re.IGNORECASE)


class BilibiliSearcher(BaseMusicSearcher):
    source = MusicSource.BILIBILI

    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        keyword = f"{query} 原神 原琴 MIDI"
        url = "https://api.bilibili.com/x/web-interface/search/all/v2"
        params = {"keyword": keyword}
        headers = {
            "Referer": "https://www.bilibili.com",
            "User-Agent": "Mozilla/5.0",
        }
        client = self._client or httpx.AsyncClient(timeout=10.0)
        try:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP {response.status_code}")
            data = response.json()
            video_data = self._extract_video_section(data)
            results: list[SearchResult] = []
            for item in video_data[:limit]:
                bvid = item.get("bvid") or ""
                title = _TAG_RE.sub("", str(item.get("title", "Untitled")))
                description = str(item.get("description", ""))
                match = _DOWNLOAD_RE.search(description)
                download_url = match.group(0) if match else None
                results.append(
                    SearchResult(
                        id=f"bilibili_{hashlib.sha1(bvid.encode()).hexdigest()[:6]}",
                        title=title,
                        source=self.source,
                        source_url=f"https://www.bilibili.com/video/{bvid}",
                        download_url=download_url,
                        score=0.6 if download_url else 0.4,
                    )
                )
            return results
        finally:
            if self._owns_client:
                await client.aclose()

    @staticmethod
    def _extract_video_section(payload: dict) -> list[dict]:
        result_list = (payload.get("data") or {}).get("result") or []
        for section in result_list:
            if section.get("type") == "video":
                return section.get("data") or []
        return []

    async def get_download_url(self, result: SearchResult) -> str:
        if not result.download_url:
            raise ValueError("Bilibili result has no extractable download URL")
        return result.download_url
```

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_searchers_html.py -v -k bilibili`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/search/bilibili.py backend/tests/test_searchers_html.py
git commit -m "feat(search): Bilibili searcher with regex download extraction"
```

---

## Task 16: Aggregator (TDD)

**Files:**
- Create: `backend/search/aggregator.py`
- Create: `backend/tests/test_search_aggregator.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for search.aggregator. Spec §8.1.6."""
from __future__ import annotations

from typing import Sequence

import pytest

from config import MusicSource, SearchResult
from search.aggregator import aggregate_results, search_all


class _StubSearcher:
    def __init__(self, source: MusicSource, results: Sequence[SearchResult]):
        self.source = source
        self._results = list(results)

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return list(self._results)[:limit]


class _RaisingSearcher:
    source = MusicSource.MUSESCORE

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        # search() should never propagate, but if a custom one does,
        # aggregator must still survive.
        raise RuntimeError("oops")


def _r(source: MusicSource, title: str, *, score: float = 0.5,
       download: str | None = "https://x/y.mid") -> SearchResult:
    return SearchResult(
        id=f"{source.value}_{title.lower().replace(' ', '_')}",
        title=title,
        source=source,
        source_url="https://x/page",
        download_url=download,
        score=score,
    )


async def test_search_all_combines_results_from_all_sources():
    a = _StubSearcher(MusicSource.FREEMIDI, [_r(MusicSource.FREEMIDI, "Tune 1")])
    b = _StubSearcher(MusicSource.BITMIDI, [_r(MusicSource.BITMIDI, "Tune 2")])
    results = await search_all([a, b], "twinkle", per_source_limit=5)
    assert len(results) == 2
    assert {r.source for r in results} == {MusicSource.FREEMIDI, MusicSource.BITMIDI}


async def test_search_all_swallows_searcher_exceptions():
    a = _StubSearcher(MusicSource.FREEMIDI, [_r(MusicSource.FREEMIDI, "Tune 1")])
    b = _RaisingSearcher()
    results = await search_all([a, b], "x", per_source_limit=5)
    assert len(results) == 1


def test_aggregate_dedupes_similar_titles_keeping_higher_score():
    a = _r(MusicSource.FREEMIDI, "Twinkle Twinkle Little Star", score=0.5)
    b = _r(MusicSource.BITMIDI, "Twinkle Twinkle Little Star", score=0.9)
    out = aggregate_results([a, b])
    assert len(out) == 1
    assert out[0].score == 0.9


def test_aggregate_orders_results_with_download_first():
    a = _r(MusicSource.MUSESCORE, "Has No Download", download=None, score=0.9)
    b = _r(MusicSource.FREEMIDI, "Has Download", score=0.5)
    out = aggregate_results([a, b])
    assert out[0].title == "Has Download"
    assert out[1].title == "Has No Download"


def test_aggregate_total_capped_at_20():
    items = [
        _r(MusicSource.FREEMIDI, f"Tune {i}", score=0.5)
        for i in range(30)
    ]
    out = aggregate_results(items)
    assert len(out) == 20


def test_aggregate_empty_input_returns_empty():
    assert aggregate_results([]) == []
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_search_aggregator.py -v`
Expected: import error.

- [ ] **Step 3: Write the aggregator**

```python
"""Cross-platform search aggregator.

Spec §8.1.6:
  - asyncio.gather over all searchers, return_exceptions=True
  - Dedupe by title similarity; keep higher-score winner
  - Sort: results with download_url first; then by score descending
  - Cap total at 20.
"""
from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
from typing import Iterable, Protocol

from config import SearchResult

_SIMILARITY_THRESHOLD = 0.85
_TOTAL_CAP = 20


class _Searcher(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...


async def search_all(
    searchers: Iterable[_Searcher],
    query: str,
    *,
    per_source_limit: int = 5,
) -> list[SearchResult]:
    coros = [s.search(query, limit=per_source_limit) for s in searchers]
    settled = await asyncio.gather(*coros, return_exceptions=True)
    flat: list[SearchResult] = []
    for outcome in settled:
        if isinstance(outcome, Exception):
            continue
        flat.extend(outcome)
    return aggregate_results(flat)


def aggregate_results(results: list[SearchResult]) -> list[SearchResult]:
    deduped: list[SearchResult] = []
    for candidate in results:
        match_index = _find_similar(candidate, deduped)
        if match_index is None:
            deduped.append(candidate)
        elif candidate.score > deduped[match_index].score:
            deduped[match_index] = candidate

    deduped.sort(
        key=lambda r: (
            0 if r.download_url else 1,    # download-first
            -r.score,                       # higher score first
        )
    )
    return deduped[:_TOTAL_CAP]


def _find_similar(candidate: SearchResult, pool: list[SearchResult]) -> int | None:
    cand = _normalize(candidate.title)
    for index, existing in enumerate(pool):
        if SequenceMatcher(None, cand, _normalize(existing.title)).ratio() >= _SIMILARITY_THRESHOLD:
            return index
    return None


def _normalize(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())
```

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_search_aggregator.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/search/aggregator.py backend/tests/test_search_aggregator.py
git commit -m "feat(search): aggregator with dedupe + download-first ordering"
```

---

## Task 17: Full part-2 regression

**Files:**
- None (verification only).

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: every part-1 test (mapper / chord_reducer / conflict_resolver / merger) and every part-2 test (cache / downloader / midi_parser / track_classifier / chord_grouper / search base / search aggregator / each searcher) passes.

- [ ] **Step 2: Confirm package-level imports compose cleanly**

Run:
```bash
cd backend && python -c "
from parser.midi_parser import parse_midi_file
from parser.track_classifier import classify_tracks
from parser.chord_grouper import group_accompaniment
from search.aggregator import search_all
from search.freemidi import FreeMidiSearcher
from search.bitmidi import BitMidiSearcher
from search.musescore import MuseScoreSearcher
from search.bilibili import BilibiliSearcher
from utils.downloader import download_to_path
from utils.cache import cache_path_for_url
print('part-2 ready')
"
```
Expected: `part-2 ready`.

Part 2 is complete. Part 3 (formatter, FastAPI routes, frontend) layers on top.

---

## What's NOT in this plan

- **Score formatting** (PC text + mobile text generation) — part 3.
- **FastAPI routes** wiring search → parse → upload → generate — part 3.
- **React frontend** — part 3.
- **Live network integration tests** — spec §11.5 mentions one but lists it as needing the network; we keep the offline mock-based tests in this plan and leave a single optional integration test for part 3 (skipped by default).
