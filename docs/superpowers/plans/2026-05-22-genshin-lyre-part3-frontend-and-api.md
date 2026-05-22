# Genshin Lyre — Part 3: Formatter + API + Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the user-facing layer: PC + mobile score text formatter, the FastAPI routes that compose part 1 (mapper + arranger) with part 2 (parser + search + download), and the React SPA (search → results → track config → score viewer).

**Architecture:** `formatter/score_formatter.py` is a pure function over a `VersionScore` that fills in `pc_score` and `mobile_score` text per spec §8.5. `main.py` registers four routes (`/api/search`, `/api/parse`, `/api/upload`, `/api/generate`) that orchestrate parser + classifier + chord-grouper + arranger + formatter, using a token-keyed in-memory store for parsed-file lifetimes. The React frontend uses Vite + Tailwind, four pages on react-router with router-state-based handoff between pages, plus a single Axios client.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn (backend); React 18, Vite, Tailwind, Axios, react-router-dom (frontend). Builds on parts 1 and 2.

---

## File Structure

```
backend/
├── main.py                          # FastAPI app + routes
├── formatter/
│   ├── __init__.py
│   └── score_formatter.py           # fill pc_score + mobile_score on VersionScore
├── api/
│   ├── __init__.py
│   ├── store.py                     # token → ParsedMidi in-memory store
│   ├── routes_search.py             # /api/search
│   ├── routes_parse.py              # /api/parse, /api/upload
│   ├── routes_generate.py           # /api/generate
│   └── errors.py                    # ApiError + handlers
└── tests/
    ├── test_score_formatter.py
    ├── test_routes_search.py
    ├── test_routes_parse.py
    └── test_routes_generate.py

frontend/
├── package.json
├── vite.config.js
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── .env.example
└── src/
    ├── main.jsx
    ├── App.jsx                      # router config
    ├── api/
    │   └── client.js                # axios + 4 API helpers
    ├── pages/
    │   ├── SearchPage.jsx
    │   ├── ResultsPage.jsx
    │   ├── TrackConfigPage.jsx
    │   └── ScorePage.jsx
    ├── components/
    │   ├── SearchBar.jsx
    │   ├── ResourceCard.jsx
    │   ├── TrackPanel.jsx
    │   ├── VersionTabs.jsx
    │   ├── ScoreDisplay.jsx
    │   └── LoadingSpinner.jsx
    └── styles/
        └── global.css

README.md                            # project root
```

**Responsibility split:**
- `formatter/score_formatter.py`: pure transform from `VersionScore.notes` → `(pc_score, mobile_score)`. No I/O. Returns a new `VersionScore` rather than mutating.
- `api/store.py`: dict-backed token store with TTL-style lookup. No I/O.
- Each `routes_*.py`: one file per route group; uses Pydantic request models defined inline.
- `api/errors.py`: single source of truth for error codes + HTTP statuses.
- `main.py`: composition root only — instantiates app, registers routers, sets CORS, registers the global exception handler.
- React pages do navigation + form state; components are presentational.

---

## Task 1: Score formatter tests (RED)

**Files:**
- Create: `backend/tests/test_score_formatter.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for formatter.score_formatter. Spec §8.5."""
from __future__ import annotations

from config import (
    ChordPosition,
    MappedNote,
    ScoreVersion,
    TrackRole,
    VersionScore,
    VersionStats,
)
from formatter.score_formatter import format_version_score


def _note(
    *, key_pc: str, key_mobile: str, start: int, duration: int = 240,
    role: TrackRole = TrackRole.MELODY, out_of_range: bool = False,
) -> MappedNote:
    return MappedNote(
        original_midi=60,
        mapped_midi=60,
        key_pc=key_pc,
        key_mobile=key_mobile,
        start_tick=start,
        duration_tick=duration,
        track_role=role,
        is_out_of_range=out_of_range,
    )


def _version(notes: list[MappedNote]) -> VersionScore:
    return VersionScore(
        version=ScoreVersion.MELODY_ONLY,
        version_label="纯旋律版",
        notes=notes,
        statistics=VersionStats(
            total_notes=len(notes),
            melody_notes=len(notes),
            accompaniment_notes=0,
            out_of_range_count=sum(1 for n in notes if n.is_out_of_range),
            semitone_count=0,
            chord_reduced_count=0,
            max_simultaneous_keys=1,
        ),
    )


class TestSimpleSequences:
    def test_single_notes_separated_by_spaces(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="S", key_mobile="2", start=240),
            _note(key_pc="D", key_mobile="3", start=480),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=480)
        assert "A S D" in out.pc_score
        assert "1 2 3" in out.mobile_score

    def test_empty_input_returns_empty_strings(self):
        out = format_version_score(_version([]), ticks_per_beat=480)
        assert out.pc_score == ""
        assert out.mobile_score == ""


class TestRestMarker:
    def test_more_than_one_beat_gap_inserts_dash(self):
        # 480 ticks/beat. Gap of 2 beats between notes → ' - '.
        notes = [
            _note(key_pc="A", key_mobile="1", start=0, duration=240),
            _note(key_pc="S", key_mobile="2", start=240 + 960),  # 2 beats of silence after
        ]
        out = format_version_score(_version(notes), ticks_per_beat=480)
        assert " - " in out.pc_score
        assert " - " in out.mobile_score


class TestChordBrackets:
    def test_simultaneous_notes_wrapped_in_parens(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="D", key_mobile="3", start=10),
            _note(key_pc="G", key_mobile="5", start=20),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=480)
        assert "(ADG)" in out.pc_score
        # Mobile chord uses concatenation without spaces inside parens.
        assert "(135)" in out.mobile_score


class TestOutOfRangeBrackets:
    def test_out_of_range_pc_wrapped_in_square_brackets(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="Q", key_mobile="+1", start=240, out_of_range=True),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=480)
        assert "[Q]" in out.pc_score
        assert "[+1]" in out.mobile_score


class TestChordReducedNotesExcluded:
    def test_chord_reduced_notes_skipped(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="D", key_mobile="3", start=0),
        ]
        notes[1].is_chord_reduced = True
        out = format_version_score(_version(notes), ticks_per_beat=480)
        assert "D" not in out.pc_score
        assert "3" not in out.mobile_score
        assert "A" in out.pc_score


class TestLineWrapping:
    def test_lines_wrap_at_16_notes(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=240 * i, duration=240)
            for i in range(20)
        ]
        out = format_version_score(_version(notes), ticks_per_beat=480)
        lines = [line for line in out.pc_score.split("\n") if line]
        # 20 single notes → 16 on first line, 4 on second.
        assert len(lines) == 2
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_score_formatter.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_score_formatter.py
git commit -m "test(formatter): add score formatter specification tests"
```

---

## Task 2: Score formatter implementation (GREEN)

**Files:**
- Create: `backend/formatter/__init__.py` (empty)
- Create: `backend/formatter/score_formatter.py`

- [ ] **Step 1: Create empty package init**

Create `backend/formatter/__init__.py` as an empty file.

- [ ] **Step 2: Write the formatter**

```python
"""Score text formatter.

Pure transform: VersionScore + ticks_per_beat → VersionScore with
pc_score and mobile_score populated. Spec §8.5.

Rules:
  - Notes whose start_tick differs by ≤ 30 ticks group into a chord token.
    PC chord: "(ADG)" — uppercase letters concatenated inside parens.
    Mobile chord: "(135)" — sign+digit tokens concatenated.
  - Out-of-range notes wrap in square brackets: "[Q]" / "[+1]". For chord
    members that are out of range, each member is wrapped individually
    inside the chord parens, e.g. "(A[Q]D)".
  - A gap > 1 beat (i.e. > ticks_per_beat) between successive groups
    inserts " - " between them.
  - Lines wrap to keep at most 16 tokens per line.
  - Notes with is_chord_reduced=True are excluded from output entirely.
"""
from __future__ import annotations

from config import MappedNote, VersionScore

CHORD_TOLERANCE_TICKS = 30
LINE_TOKEN_LIMIT = 16


def format_version_score(
    version: VersionScore,
    *,
    ticks_per_beat: int,
) -> VersionScore:
    """Return a new VersionScore with pc_score / mobile_score filled in."""
    visible = [n for n in version.notes if not n.is_chord_reduced]
    if not visible:
        return version.model_copy(update={"pc_score": "", "mobile_score": ""})

    visible.sort(key=lambda n: n.start_tick)
    groups = _group_simultaneous(visible)

    pc_tokens = _build_token_stream(groups, ticks_per_beat, mode="pc")
    mobile_tokens = _build_token_stream(groups, ticks_per_beat, mode="mobile")
    return version.model_copy(
        update={
            "pc_score": _wrap_lines(pc_tokens),
            "mobile_score": _wrap_lines(mobile_tokens),
        }
    )


def _group_simultaneous(notes: list[MappedNote]) -> list[list[MappedNote]]:
    groups: list[list[MappedNote]] = [[notes[0]]]
    for note in notes[1:]:
        if abs(note.start_tick - groups[-1][0].start_tick) <= CHORD_TOLERANCE_TICKS:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _build_token_stream(
    groups: list[list[MappedNote]],
    ticks_per_beat: int,
    *,
    mode: str,
) -> list[str]:
    tokens: list[str] = []
    prev_end_tick: int | None = None
    for group in groups:
        group_start = min(n.start_tick for n in group)
        if prev_end_tick is not None:
            gap = group_start - prev_end_tick
            if gap > ticks_per_beat:
                tokens.append("-")
        tokens.append(_render_group(group, mode=mode))
        prev_end_tick = max(n.start_tick + n.duration_tick for n in group)
    return tokens


def _render_group(group: list[MappedNote], *, mode: str) -> str:
    if len(group) == 1:
        return _render_single(group[0], mode=mode)
    inner = "".join(_render_single(n, mode=mode) for n in group)
    return f"({inner})"


def _render_single(note: MappedNote, *, mode: str) -> str:
    base = note.key_pc if mode == "pc" else note.key_mobile
    return f"[{base}]" if note.is_out_of_range else base


def _wrap_lines(tokens: list[str]) -> str:
    lines: list[str] = []
    current: list[str] = []
    note_count = 0  # count of non-rest tokens
    for token in tokens:
        current.append(token)
        if token != "-":
            note_count += 1
        if note_count >= LINE_TOKEN_LIMIT:
            lines.append(" ".join(current))
            current = []
            note_count = 0
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)
```

- [ ] **Step 3: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_score_formatter.py -v`
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/formatter/__init__.py backend/formatter/score_formatter.py
git commit -m "feat(formatter): VersionScore text formatter (PC + mobile)"
```

---

## Task 3: API errors module

**Files:**
- Create: `backend/api/__init__.py` (empty)
- Create: `backend/api/errors.py`

- [ ] **Step 1: Create empty api package init**

Create `backend/api/__init__.py` as an empty file.

- [ ] **Step 2: Write `backend/api/errors.py`**

Single source of truth for error codes per spec §10.

```python
"""Standard error codes and ApiError exception.

Spec §10. The route handlers raise ApiError; the global handler in
main.py converts them to the documented JSON error envelope.
"""
from __future__ import annotations

from fastapi import status
from pydantic import BaseModel


class ApiErrorPayload(BaseModel):
    error: str
    message: str
    detail: str | None = None


class ApiError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.detail = detail

    def to_payload(self) -> ApiErrorPayload:
        return ApiErrorPayload(error=self.code, message=self.message, detail=self.detail)


# Code → (HTTP status, default user-facing message). Matches spec §10 table.
ERROR_CATALOG: dict[str, tuple[int, str]] = {
    "SEARCH_FAILED": (status.HTTP_500_INTERNAL_SERVER_ERROR, "全部搜索源不可用，请稍后重试。"),
    "DOWNLOAD_FAILED": (status.HTTP_400_BAD_REQUEST, "MIDI 文件下载失败。"),
    "FILE_TOO_LARGE": (status.HTTP_400_BAD_REQUEST, "文件超过 5MB 限制。"),
    "PARSE_FAILED": (status.HTTP_400_BAD_REQUEST, "MIDI 解析失败，请尝试其他文件。"),
    "INVALID_FILE_TYPE": (status.HTTP_400_BAD_REQUEST, "请上传 .mid 或 .midi 文件。"),
    "NO_MELODY_TRACK": (status.HTTP_400_BAD_REQUEST, "请至少指定一条主旋律轨道。"),
    "FILE_NOT_FOUND": (status.HTTP_404_NOT_FOUND, "文件已过期，请重新解析。"),
    "INVALID_TRACK_INDEX": (status.HTTP_400_BAD_REQUEST, "轨道索引无效。"),
}


def make_error(code: str, *, detail: str | None = None) -> ApiError:
    http_status, default_message = ERROR_CATALOG[code]
    return ApiError(
        code=code,
        message=default_message,
        http_status=http_status,
        detail=detail,
    )
```

- [ ] **Step 3: Quick import check**

Run: `cd backend && python -c "from api.errors import make_error, ApiError; print(make_error('PARSE_FAILED').code)"`
Expected: `PARSE_FAILED`.

- [ ] **Step 4: Commit**

```bash
git add backend/api/__init__.py backend/api/errors.py
git commit -m "feat(api): ApiError + ERROR_CATALOG matching spec §10"
```

---

## Task 4: Token store (TDD)

**Files:**
- Create: `backend/api/store.py`
- Create: `backend/tests/test_store.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for api.store."""
from __future__ import annotations

import pytest

from config import ParsedMidi, ParsedTrack, TrackInfo, TrackRole
from api.store import ParsedFileStore


def _empty_parsed() -> ParsedMidi:
    return ParsedMidi(bpm=120, ticks_per_beat=480, tracks=[])


def _track_info(index: int, role: TrackRole) -> TrackInfo:
    return TrackInfo(
        index=index,
        name=f"Track {index}",
        note_count=10,
        pitch_range="C4~G4",
        preview_keys="A S D F",
        suggested_role=role,
        chord_type="none",
    )


def test_save_returns_token_with_prefix():
    store = ParsedFileStore()
    token = store.save(_empty_parsed(), "Title", track_infos=[])
    assert token.startswith("tmp_")


def test_get_returns_saved_record():
    store = ParsedFileStore()
    parsed = _empty_parsed()
    infos = [_track_info(0, TrackRole.MELODY)]
    token = store.save(parsed, "Title", track_infos=infos)
    record = store.get(token)
    assert record.parsed is parsed
    assert record.title == "Title"
    assert record.track_infos == infos


def test_get_unknown_token_raises_keyerror():
    store = ParsedFileStore()
    with pytest.raises(KeyError):
        store.get("tmp_nope")


def test_distinct_tokens_per_save():
    store = ParsedFileStore()
    a = store.save(_empty_parsed(), "A", track_infos=[])
    b = store.save(_empty_parsed(), "B", track_infos=[])
    assert a != b
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: import error.

- [ ] **Step 3: Write the store**

```python
"""In-memory store keyed by file_token.

The /api/parse and /api/upload routes save a ParsedMidi here and return
the token. /api/generate looks the record up by token. Lifetime is the
process lifetime — restart clears all tokens, which manifests as
FILE_NOT_FOUND to the client.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass

from config import ParsedMidi, TrackInfo


@dataclass(frozen=True)
class StoredRecord:
    parsed: ParsedMidi
    title: str
    track_infos: list[TrackInfo]


class ParsedFileStore:
    def __init__(self) -> None:
        self._records: dict[str, StoredRecord] = {}

    def save(
        self,
        parsed: ParsedMidi,
        title: str,
        *,
        track_infos: list[TrackInfo],
    ) -> str:
        token = f"tmp_{secrets.token_hex(8)}"
        self._records[token] = StoredRecord(
            parsed=parsed, title=title, track_infos=track_infos
        )
        return token

    def get(self, token: str) -> StoredRecord:
        return self._records[token]
```

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_store.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/store.py backend/tests/test_store.py
git commit -m "feat(api): in-memory ParsedFileStore keyed by tmp_ token"
```

---

## Task 5: /api/search route + tests

**Files:**
- Create: `backend/api/routes_search.py`
- Create: `backend/tests/test_routes_search.py`

- [ ] **Step 1: Write failing tests**

We use `TestClient` and inject a stub aggregator via dependency override.

```python
"""Tests for /api/search route."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.routes_search import get_searchers
from config import MusicSource, SearchResult
from main import app


class _StubSearcher:
    def __init__(self, source: MusicSource):
        self.source = source

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                id=f"{self.source.value}_x",
                title=f"{query} hit",
                source=self.source,
                source_url="https://example.com/x",
                download_url="https://example.com/x.mid",
                score=0.9,
            )
        ]


def _override_with_stub() -> list:
    return [_StubSearcher(MusicSource.FREEMIDI), _StubSearcher(MusicSource.BITMIDI)]


def test_search_returns_aggregated_results():
    app.dependency_overrides[get_searchers] = _override_with_stub
    try:
        client = TestClient(app)
        resp = client.get("/api/search", params={"q": "twinkle"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "twinkle"
        assert body["total"] == 2
        assert len(body["results"]) == 2
    finally:
        app.dependency_overrides.clear()


def test_search_missing_q_returns_422():
    client = TestClient(app)
    resp = client.get("/api/search")
    assert resp.status_code == 422
```

- [ ] **Step 2: Confirm RED** (will fail because `main` and `routes_search` don't exist yet)

Run: `cd backend && python -m pytest tests/test_routes_search.py -v`
Expected: import error.

- [ ] **Step 3: Write the route**

```python
"""GET /api/search route."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from search.aggregator import search_all
from search.bilibili import BilibiliSearcher
from search.bitmidi import BitMidiSearcher
from search.freemidi import FreeMidiSearcher
from search.musescore import MuseScoreSearcher

router = APIRouter(prefix="/api", tags=["search"])


def get_searchers() -> list:
    return [
        FreeMidiSearcher(),
        BitMidiSearcher(),
        MuseScoreSearcher(),
        BilibiliSearcher(),
    ]


@router.get("/search")
async def search(
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    searchers: list = Depends(get_searchers),
) -> dict:
    results = await search_all(searchers, q, per_source_limit=limit)
    return {
        "query": q,
        "total": len(results),
        "results": [r.model_dump(mode="json") for r in results],
    }
```

- [ ] **Step 4: Verify GREEN** (runs after Task 6 wires up `main.py`).

Skip running tests for now; we'll verify after Task 6.

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes_search.py backend/tests/test_routes_search.py
git commit -m "feat(api): /api/search route + tests"
```

---

## Task 6: FastAPI main app skeleton

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Write `backend/main.py`**

```python
"""FastAPI composition root.

Spec §8.6:
  - Enable CORS for http://localhost:5173
  - All routes live under /api
  - Create /tmp/genshin_lyre/ on startup
  - Global exception handler → uniform error envelope
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.errors import ApiError, ApiErrorPayload
from api.routes_search import router as search_router
from utils.cache import DEFAULT_CACHE_DIR, ensure_cache_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    yield


app = FastAPI(title="Genshin Lyre Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_payload().model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiErrorPayload(
            error="INTERNAL_ERROR",
            message="服务暂时不可用，请稍后再试。",
            detail=str(exc),
        ).model_dump(),
    )


app.include_router(search_router)
```

- [ ] **Step 2: Run the search route tests now that `main` exists**

Run: `cd backend && python -m pytest tests/test_routes_search.py -v`
Expected: 2 tests PASS.

- [ ] **Step 3: Smoke-test the app starts**

Run: `cd backend && python -c "from main import app; print(app.title)"`
Expected: `Genshin Lyre Backend`.

- [ ] **Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat(api): FastAPI app with CORS + global error handler"
```

---

## Task 7: /api/parse route + tests

**Files:**
- Create: `backend/api/routes_parse.py`
- Create: `backend/tests/test_routes_parse.py`
- Modify: `backend/main.py` (register the new router + global store)

- [ ] **Step 1: Write failing tests**

The route downloads a MIDI from the provided URL, parses it, classifies tracks, and saves a token. We mock the downloader by providing the file pre-cached.

```python
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
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_routes_parse.py -v`
Expected: import error (`routes_parse` and `file_store` don't exist).

- [ ] **Step 3: Write the route file**

```python
"""POST /api/parse and POST /api/upload."""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel

from api.errors import make_error
from api.store import ParsedFileStore
from parser.chord_grouper import group_accompaniment  # noqa: F401  (used by generate)
from parser.midi_parser import ParseError, parse_midi_file
from parser.track_classifier import classify_tracks
from utils.cache import cache_path_for_url, ensure_cache_dir, is_cached, DEFAULT_CACHE_DIR
from utils.downloader import DownloadError, download_to_path

router = APIRouter(prefix="/api", tags=["parse"])
_LOG = logging.getLogger(__name__)


class ParseRequest(BaseModel):
    result_id: str
    download_url: str
    title: str


def get_store() -> ParsedFileStore:  # overridden via main.app
    raise RuntimeError("get_store must be overridden by main.py")


@router.post("/parse")
async def parse(
    payload: ParseRequest,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    target = cache_path_for_url(payload.download_url)
    if not is_cached(payload.download_url):
        try:
            await download_to_path(payload.download_url, target)
        except DownloadError as exc:
            raise make_error("DOWNLOAD_FAILED", detail=str(exc))
    return _parse_and_save(target, payload.title, store)


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith((".mid", ".midi")):
        raise make_error("INVALID_FILE_TYPE")

    ensure_cache_dir(DEFAULT_CACHE_DIR)
    target = DEFAULT_CACHE_DIR / f"upload_{uuid.uuid4().hex}.mid"
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise make_error("FILE_TOO_LARGE")
    target.write_bytes(contents)
    title = Path(filename).stem
    return _parse_and_save(target, title, store)


def _parse_and_save(path: Path, title: str, store: ParsedFileStore) -> dict:
    try:
        parsed = parse_midi_file(path)
    except ParseError as exc:
        raise make_error("PARSE_FAILED", detail=str(exc))
    track_infos = classify_tracks(parsed)
    token = store.save(parsed, title, track_infos=track_infos)
    return {
        "file_token": token,
        "title": title,
        "bpm": parsed.bpm,
        "ticks_per_beat": parsed.ticks_per_beat,
        "tracks": [t.model_dump(mode="json") for t in track_infos],
    }
```

- [ ] **Step 4: Update `backend/main.py` to register the router and store**

Edit `backend/main.py` to add the global store and wire up the parse router. Replace the current contents with:

```python
"""FastAPI composition root.

Spec §8.6.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.errors import ApiError, ApiErrorPayload
from api.routes_parse import get_store, router as parse_router
from api.routes_search import router as search_router
from api.store import ParsedFileStore
from utils.cache import DEFAULT_CACHE_DIR, ensure_cache_dir


file_store = ParsedFileStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_cache_dir(DEFAULT_CACHE_DIR)
    yield


app = FastAPI(title="Genshin Lyre Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.dependency_overrides[get_store] = lambda: file_store


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=exc.to_payload().model_dump(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ApiErrorPayload(
            error="INTERNAL_ERROR",
            message="服务暂时不可用，请稍后再试。",
            detail=str(exc),
        ).model_dump(),
    )


app.include_router(search_router)
app.include_router(parse_router)
```

- [ ] **Step 5: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_routes_parse.py tests/test_routes_search.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/api/routes_parse.py backend/main.py backend/tests/test_routes_parse.py
git commit -m "feat(api): /api/parse and /api/upload with token store wiring"
```

---

## Task 8: /api/generate route + tests

**Files:**
- Create: `backend/api/routes_generate.py`
- Create: `backend/tests/test_routes_generate.py`
- Modify: `backend/main.py` (register the new router)

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Confirm RED**

Run: `cd backend && python -m pytest tests/test_routes_generate.py -v`
Expected: import error.

- [ ] **Step 3: Write the route**

```python
"""POST /api/generate.

Composes parser output (cached in the store) with arranger + formatter
to produce three VersionScore objects.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.errors import make_error
from api.routes_parse import get_store
from api.store import ParsedFileStore
from arranger.merger import build_three_versions
from config import (
    ChordPosition,
    LyreScore,
    MappedNote,
    ParsedNote,
    ScoreVersion,
    TrackRole,
)
from formatter.score_formatter import format_version_score
from mapper.note_mapper import map_notes
from parser.chord_grouper import group_accompaniment

router = APIRouter(prefix="/api", tags=["generate"])


class GenerateRequest(BaseModel):
    file_token: str
    title: str
    track_roles: dict[str, str]  # "0" -> "melody"


@router.post("/generate")
async def generate(
    payload: GenerateRequest,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    try:
        record = store.get(payload.file_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND")

    valid_indices = {t.index for t in record.parsed.tracks}
    parsed_roles: dict[int, TrackRole] = {}
    for raw_index, raw_role in payload.track_roles.items():
        try:
            idx = int(raw_index)
        except ValueError:
            raise make_error("INVALID_TRACK_INDEX", detail=raw_index)
        if idx not in valid_indices:
            raise make_error("INVALID_TRACK_INDEX", detail=str(idx))
        try:
            parsed_roles[idx] = TrackRole(raw_role)
        except ValueError:
            raise make_error("INVALID_TRACK_INDEX", detail=raw_role)

    if not any(role == TrackRole.MELODY for role in parsed_roles.values()):
        raise make_error("NO_MELODY_TRACK")

    melody_notes: list[MappedNote] = []
    accompaniment_notes: list[MappedNote] = []
    chord_groups: list[list[MappedNote]] = []

    for track in record.parsed.tracks:
        role = parsed_roles.get(track.index, TrackRole.IGNORED)
        if role not in (TrackRole.MELODY, TrackRole.ACCOMPANIMENT):
            continue
        # Re-tag track_role on the parsed notes before mapping.
        retagged = [
            ParsedNote(
                midi_num=n.midi_num,
                start_tick=n.start_tick,
                duration_tick=n.duration_tick,
                velocity=n.velocity,
                track_index=n.track_index,
                track_role=role,
            )
            for n in track.notes
        ]
        mapped = map_notes(retagged)
        if role == TrackRole.MELODY:
            melody_notes.extend(mapped)
        else:
            accompaniment_notes.extend(mapped)
            # Group by simultaneous start_tick (mirrors ParsedNote ordering).
            for raw_group in group_accompaniment(retagged):
                # Map indexes inside this raw group back to MappedNote objects.
                group_starts = {n.start_tick for n in raw_group}
                chord_groups.append(
                    [m for m in mapped if m.start_tick in group_starts]
                )

    versions_dict = build_three_versions(
        melody_notes=melody_notes,
        accompaniment_notes=accompaniment_notes,
        chord_groups=chord_groups,
    )

    formatted = [
        format_version_score(
            versions_dict[ScoreVersion.MELODY_ONLY],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
        format_version_score(
            versions_dict[ScoreVersion.SIMPLIFIED],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
        format_version_score(
            versions_dict[ScoreVersion.FULL],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
    ]

    score = LyreScore(
        title=payload.title,
        bpm=record.parsed.bpm,
        ticks_per_beat=record.parsed.ticks_per_beat,
        versions=formatted,
    )
    return score.model_dump(mode="json")
```

- [ ] **Step 4: Register the new router in `main.py`**

Edit `backend/main.py`. After the existing `app.include_router(parse_router)` line, append:

```python
from api.routes_generate import router as generate_router  # noqa: E402

app.include_router(generate_router)
```

- [ ] **Step 5: Verify GREEN**

Run: `cd backend && python -m pytest tests/test_routes_generate.py -v`
Expected: 5 tests PASS.

- [ ] **Step 6: Run the full backend suite**

Run: `cd backend && python -m pytest -v`
Expected: every test from parts 1, 2, and 3 so far passes.

- [ ] **Step 7: Commit**

```bash
git add backend/api/routes_generate.py backend/main.py backend/tests/test_routes_generate.py
git commit -m "feat(api): /api/generate composes arranger + formatter into three versions"
```

---

## Task 9: Backend manual smoke test

**Files:**
- None (verification only).

- [ ] **Step 1: Start the server**

Run in a background terminal: `cd backend && uvicorn main:app --port 8000 --log-level warning &`

- [ ] **Step 2: Hit /api/search with curl**

Run: `curl -s 'http://localhost:8000/api/search?q=canon&limit=2' | head -c 500`
Expected: a JSON object with `query`, `total`, and a `results` array (may be empty if all real searchers fail — that's fine; we only confirm shape).

- [ ] **Step 3: Verify the OpenAPI docs render**

Run: `curl -s http://localhost:8000/openapi.json | head -c 300`
Expected: a JSON document starting with `{"openapi":"3...`.

- [ ] **Step 4: Stop the server**

Run: `pkill -f 'uvicorn main:app'` (or stop the background process you started).

No commit — this is verification only.

---

## Task 10: Frontend scaffold (Vite + Tailwind)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/postcss.config.js`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/.env.example`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/styles/global.css`

- [ ] **Step 1: Write `frontend/package.json`**

```json
{
  "name": "genshin-lyre-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "axios": "^1.7.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Write `frontend/vite.config.js`**

```javascript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
```

- [ ] **Step 3: Write `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

- [ ] **Step 4: Write `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Write `frontend/.env.example`**

```
VITE_API_URL=http://localhost:8000
```

- [ ] **Step 6: Write `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>原神原琴 AI 编谱</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Write `frontend/src/styles/global.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

body {
  @apply bg-slate-50 text-slate-900 antialiased;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
}

.score-mono {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
```

- [ ] **Step 8: Write `frontend/src/main.jsx`**

```javascript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./styles/global.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 9: Install + verify build**

Run:
```bash
cd frontend && npm install
```
Expected: install completes without errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "chore(frontend): scaffold Vite + Tailwind + React"
```

---

## Task 11: API client

**Files:**
- Create: `frontend/src/api/client.js`

- [ ] **Step 1: Write `frontend/src/api/client.js`**

```javascript
import axios from "axios";

const baseURL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({ baseURL, timeout: 30_000 });

client.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response && err.response.data && err.response.data.message) {
      err.userMessage = err.response.data.message;
    } else {
      err.userMessage = "服务暂时不可用，请稍后重试。";
    }
    return Promise.reject(err);
  }
);

export async function searchMusic(query, limit = 5) {
  const resp = await client.get("/api/search", { params: { q: query, limit } });
  return resp.data;
}

export async function parseResource({ result_id, download_url, title }) {
  const resp = await client.post("/api/parse", { result_id, download_url, title });
  return resp.data;
}

export async function uploadMidi(file) {
  const form = new FormData();
  form.append("file", file);
  const resp = await client.post("/api/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function generateScore({ file_token, title, track_roles }) {
  const resp = await client.post("/api/generate", { file_token, title, track_roles });
  return resp.data;
}

export default client;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/client.js
git commit -m "feat(frontend): API client with 4 helpers and error interceptor"
```

---

## Task 12: App router + LoadingSpinner

**Files:**
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/components/LoadingSpinner.jsx`

- [ ] **Step 1: Write `frontend/src/components/LoadingSpinner.jsx`**

```javascript
export default function LoadingSpinner({ label }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-slate-700" />
      {label && <p className="text-sm text-slate-600">{label}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/App.jsx`**

```javascript
import { Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import TrackConfigPage from "./pages/TrackConfigPage.jsx";
import ScorePage from "./pages/ScorePage.jsx";

export default function App() {
  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/results" element={<ResultsPage />} />
        <Route path="/tracks" element={<TrackConfigPage />} />
        <Route path="/score" element={<ScorePage />} />
      </Routes>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/LoadingSpinner.jsx
git commit -m "feat(frontend): App router config and LoadingSpinner"
```

---

## Task 13: SearchPage + SearchBar

**Files:**
- Create: `frontend/src/components/SearchBar.jsx`
- Create: `frontend/src/pages/SearchPage.jsx`

- [ ] **Step 1: Write `frontend/src/components/SearchBar.jsx`**

```javascript
import { useState } from "react";

export default function SearchBar({ onSubmit, initialValue = "" }) {
  const [value, setValue] = useState(initialValue);

  function handleSubmit(e) {
    e.preventDefault();
    const q = value.trim();
    if (q.length === 0) return;
    onSubmit(q);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="请输入曲名，如：小星星、Canon in D"
        className="flex-1 rounded-lg border border-slate-300 px-4 py-3 text-base focus:border-slate-700 focus:outline-none"
      />
      <button
        type="submit"
        className="rounded-lg bg-slate-900 px-6 py-3 text-base text-white hover:bg-slate-700"
      >
        搜索
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Write `frontend/src/pages/SearchPage.jsx`**

```javascript
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchMusic } from "../api/client.js";
import SearchBar from "../components/SearchBar.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

const HISTORY_KEY = "lyre.searchHistory";

function readHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function pushHistory(query) {
  const cur = readHistory().filter((q) => q !== query);
  cur.unshift(query);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(cur.slice(0, 10)));
}

export default function SearchPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState(readHistory());

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    try {
      const data = await searchMusic(query);
      pushHistory(query);
      setHistory(readHistory());
      navigate("/results", { state: { query, results: data.results } });
    } catch (err) {
      setError(err.userMessage || "搜索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold">原神原琴 AI 编谱</h1>
      <p className="mb-8 text-slate-600">输入曲名，自动生成三版可弹奏琴谱。</p>
      <SearchBar onSubmit={handleSearch} />

      {loading && (
        <LoadingSpinner label="正在同时搜索 FreeMIDI、BitMIDI、MuseScore、B站…" />
      )}
      {error && (
        <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {history.length > 0 && !loading && (
        <section className="mt-10">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            最近搜索
          </h2>
          <div className="flex flex-wrap gap-2">
            {history.map((q) => (
              <button
                key={q}
                onClick={() => handleSearch(q)}
                className="rounded-full border border-slate-300 px-3 py-1 text-sm hover:border-slate-700"
              >
                {q}
              </button>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SearchBar.jsx frontend/src/pages/SearchPage.jsx
git commit -m "feat(frontend): SearchPage with history + loading + error states"
```

---

## Task 14: ResultsPage + ResourceCard

**Files:**
- Create: `frontend/src/components/ResourceCard.jsx`
- Create: `frontend/src/pages/ResultsPage.jsx`

- [ ] **Step 1: Write `frontend/src/components/ResourceCard.jsx`**

```javascript
const SOURCE_LABELS = {
  freemidi: "FreeMIDI",
  bitmidi: "BitMIDI",
  musescore: "MuseScore",
  bilibili: "B站",
};

function truncate(text, n = 40) {
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

export default function ResourceCard({ result, onSelect }) {
  const hasDownload = Boolean(result.download_url);
  const meta = [
    result.duration_seconds ? `${result.duration_seconds}s` : null,
    result.file_size_kb ? `${result.file_size_kb}KB` : null,
    result.track_count ? `${result.track_count} 轨道` : null,
  ].filter(Boolean);

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h3 className="text-base font-medium leading-tight">{truncate(result.title, 40)}</h3>
        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {SOURCE_LABELS[result.source] || result.source}
        </span>
      </div>
      {meta.length > 0 && (
        <p className="mb-3 text-xs text-slate-500">{meta.join(" · ")}</p>
      )}
      {result.preview_keys && (
        <p className="mb-3 score-mono text-xs text-slate-700">{result.preview_keys}</p>
      )}
      <div className="flex justify-end">
        {hasDownload ? (
          <button
            onClick={() => onSelect(result)}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            选择此版本
          </button>
        ) : (
          <a
            href={result.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
          >
            前往下载
          </a>
        )}
      </div>
    </article>
  );
}
```

- [ ] **Step 2: Write `frontend/src/pages/ResultsPage.jsx`**

```javascript
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { parseResource, uploadMidi } from "../api/client.js";
import ResourceCard from "../components/ResourceCard.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "freemidi", label: "FreeMIDI" },
  { key: "bitmidi", label: "BitMIDI" },
  { key: "musescore", label: "MuseScore" },
  { key: "bilibili", label: "B站" },
];

export default function ResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { query = "", results = [] } = location.state || {};
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!location.state) navigate("/");
  }, [location.state, navigate]);

  const filtered = useMemo(
    () => (filter === "all" ? results : results.filter((r) => r.source === filter)),
    [filter, results]
  );

  async function handleSelect(result) {
    setBusy(true);
    setError(null);
    try {
      const data = await parseResource({
        result_id: result.id,
        download_url: result.download_url,
        title: result.title,
      });
      navigate("/tracks", { state: data });
    } catch (err) {
      setError(err.userMessage || "下载或解析失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const data = await uploadMidi(file);
      navigate("/tracks", { state: data });
    } catch (err) {
      setError(err.userMessage || "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 pb-32">
      <header className="mb-6">
        <button onClick={() => navigate("/")} className="mb-3 text-sm text-slate-500 hover:text-slate-900">
          ← 重新搜索
        </button>
        <h1 className="text-2xl font-bold">"{query}" 的搜索结果</h1>
        <p className="text-sm text-slate-600">共 {results.length} 条</p>
      </header>

      <nav className="mb-5 flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-full border px-3 py-1 text-sm ${
              filter === f.key
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 hover:border-slate-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </nav>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {busy && <LoadingSpinner label="正在解析 MIDI…" />}

      {!busy && (
        <div className="space-y-3">
          {filtered.map((r) => (
            <ResourceCard key={r.id} result={r} onSelect={handleSelect} />
          ))}
          {filtered.length === 0 && (
            <p className="py-12 text-center text-slate-500">
              没有结果，可尝试英文曲名或上传本地 MIDI。
            </p>
          )}
        </div>
      )}

      <div className="fixed bottom-0 left-0 right-0 border-t border-slate-200 bg-white px-4 py-3">
        <label className="mx-auto flex max-w-3xl cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 py-2 text-sm hover:border-slate-700">
          上传本地 MIDI 文件
          <input
            type="file"
            accept=".mid,.midi"
            onChange={handleUpload}
            className="hidden"
          />
        </label>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ResourceCard.jsx frontend/src/pages/ResultsPage.jsx
git commit -m "feat(frontend): ResultsPage with filter + upload + parse handoff"
```

---

## Task 15: TrackConfigPage + TrackPanel

**Files:**
- Create: `frontend/src/components/TrackPanel.jsx`
- Create: `frontend/src/pages/TrackConfigPage.jsx`

- [ ] **Step 1: Write `frontend/src/components/TrackPanel.jsx`**

```javascript
const ROLE_OPTIONS = [
  { value: "melody", label: "主旋律" },
  { value: "accompaniment", label: "伴奏" },
  { value: "bass", label: "低音" },
  { value: "ignored", label: "忽略" },
];

const CHORD_TYPE_LABELS = {
  chordal: "柱式和弦",
  arpeggiated: "分解和弦",
  mixed: "混合",
  none: "",
};

export default function TrackPanel({ tracks, roles, onChange }) {
  return (
    <ul className="space-y-3">
      {tracks.map((track) => {
        const value = roles[String(track.index)] ?? track.suggested_role;
        const recommended = track.suggested_role;
        return (
          <li
            key={track.index}
            className="rounded-xl border border-slate-200 bg-white p-4"
          >
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 className="text-sm font-medium">{track.name}</h3>
              <span className="text-xs text-slate-500">
                {track.note_count} 音 · {track.pitch_range}
              </span>
            </div>
            <p className="mb-3 score-mono text-xs text-slate-600">
              {track.preview_keys}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {ROLE_OPTIONS.map((opt) => {
                const active = value === opt.value;
                const isRec = recommended === opt.value;
                return (
                  <label
                    key={opt.value}
                    className={`relative cursor-pointer rounded-full border px-3 py-1 text-sm ${
                      active
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <input
                      type="radio"
                      name={`role-${track.index}`}
                      value={opt.value}
                      checked={active}
                      onChange={() => onChange(track.index, opt.value)}
                      className="sr-only"
                    />
                    {opt.label}
                    {isRec && (
                      <span className="ml-1 rounded bg-amber-200 px-1 text-[10px] text-amber-900">
                        推荐
                      </span>
                    )}
                  </label>
                );
              })}
              {value === "accompaniment" && CHORD_TYPE_LABELS[track.chord_type] && (
                <span className="ml-1 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {CHORD_TYPE_LABELS[track.chord_type]}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 2: Write `frontend/src/pages/TrackConfigPage.jsx`**

```javascript
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { generateScore } from "../api/client.js";
import TrackPanel from "../components/TrackPanel.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

export default function TrackConfigPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const initial = location.state || null;

  const [roles, setRoles] = useState(() =>
    initial
      ? Object.fromEntries(initial.tracks.map((t) => [String(t.index), t.suggested_role]))
      : {}
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!initial) navigate("/");
  }, [initial, navigate]);

  if (!initial) return null;

  const hasMelody = Object.values(roles).includes("melody");

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const data = await generateScore({
        file_token: initial.file_token,
        title: initial.title,
        track_roles: roles,
      });
      navigate("/score", {
        state: { score: data, fileToken: initial.file_token, tracks: initial.tracks },
      });
    } catch (err) {
      setError(err.userMessage || "生成失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 pb-32">
      <button onClick={() => navigate(-1)} className="mb-3 text-sm text-slate-500 hover:text-slate-900">
        ← 返回
      </button>
      <h1 className="mb-1 text-2xl font-bold">配置轨道</h1>
      <p className="mb-2 text-sm text-slate-600">
        {initial.title} · BPM {initial.bpm}
      </p>
      <p className="mb-6 text-xs text-slate-500">
        系统已自动识别轨道角色，您可根据实际情况调整。分解和弦伴奏将完整保留；柱式和弦在简化版中将自动精简为
        2~3 个关键音。
      </p>

      <TrackPanel
        tracks={initial.tracks}
        roles={roles}
        onChange={(idx, value) =>
          setRoles((prev) => ({ ...prev, [String(idx)]: value }))
        }
      />

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {busy && <LoadingSpinner label="正在生成三版琴谱…" />}

      <div className="fixed bottom-0 left-0 right-0 border-t border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <span className="text-xs text-slate-500">
            {hasMelody ? "已就绪" : "请至少指定一条主旋律轨道"}
          </span>
          <button
            onClick={handleGenerate}
            disabled={!hasMelody || busy}
            className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            生成琴谱
          </button>
        </div>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TrackPanel.jsx frontend/src/pages/TrackConfigPage.jsx
git commit -m "feat(frontend): TrackConfigPage with role selection and melody guard"
```

---

## Task 16: ScorePage + VersionTabs + ScoreDisplay

**Files:**
- Create: `frontend/src/components/VersionTabs.jsx`
- Create: `frontend/src/components/ScoreDisplay.jsx`
- Create: `frontend/src/pages/ScorePage.jsx`

- [ ] **Step 1: Write `frontend/src/components/VersionTabs.jsx`**

```javascript
export default function VersionTabs({ versions, active, onSelect }) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
      {versions.map((v) => (
        <button
          key={v.version}
          onClick={() => onSelect(v.version)}
          className={`flex-1 rounded-md px-3 py-2 text-sm font-medium ${
            active === v.version
              ? "bg-white shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          {v.version_label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Write `frontend/src/components/ScoreDisplay.jsx`**

```javascript
function highlightOutOfRange(line) {
  // Replace [TOKEN] with a highlighted span; preserve everything else.
  const parts = [];
  const regex = /\[([^\]]+)\]/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = regex.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(line.slice(lastIndex, match.index));
    }
    parts.push(
      <span key={`oor-${key++}`} className="rounded bg-amber-200 px-1 text-amber-900">
        {match[1]}
      </span>
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < line.length) {
    parts.push(line.slice(lastIndex));
  }
  return parts;
}

export default function ScoreDisplay({ text }) {
  if (!text) {
    return <p className="text-slate-500">本版本暂无音符。</p>;
  }
  const lines = text.split("\n");
  return (
    <pre className="score-mono whitespace-pre-wrap text-base leading-relaxed">
      {lines.map((line, i) => (
        <div key={i}>{highlightOutOfRange(line)}</div>
      ))}
    </pre>
  );
}
```

- [ ] **Step 3: Write `frontend/src/pages/ScorePage.jsx`**

```javascript
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import VersionTabs from "../components/VersionTabs.jsx";
import ScoreDisplay from "../components/ScoreDisplay.jsx";

const MODES = [
  { key: "pc", label: "PC 字母谱" },
  { key: "mobile", label: "手机数字谱" },
];

export default function ScorePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const score = location.state?.score;
  const fileToken = location.state?.fileToken;
  const tracks = location.state?.tracks;

  useEffect(() => {
    if (!score) navigate("/");
  }, [score, navigate]);

  const [activeVersion, setActiveVersion] = useState("simplified");
  const [activeMode, setActiveMode] = useState("pc");
  const [statsOpen, setStatsOpen] = useState(false);

  const current = useMemo(
    () => score?.versions?.find((v) => v.version === activeVersion) || null,
    [score, activeVersion]
  );

  if (!score || !current) return null;

  const text = activeMode === "pc" ? current.pc_score : current.mobile_score;

  function handleCopy() {
    navigator.clipboard.writeText(text || "");
  }

  function handleDownload() {
    const blob = new Blob([text || ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${score.title}-${current.version_label}-${activeMode}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{score.title}</h1>
        <p className="text-sm text-slate-600">
          BPM {score.bpm} · {score.versions.length} 个版本
        </p>
      </header>

      <VersionTabs
        versions={score.versions}
        active={activeVersion}
        onSelect={setActiveVersion}
      />

      <div className="mt-4 mb-3 flex gap-2">
        {MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => setActiveMode(m.key)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              activeMode === m.key
                ? "bg-slate-900 text-white"
                : "border border-slate-300 hover:border-slate-700"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <ScoreDisplay text={text} />
      </section>

      <details
        className="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-sm"
        open={statsOpen}
        onToggle={(e) => setStatsOpen(e.currentTarget.open)}
      >
        <summary className="cursor-pointer font-medium">统计信息</summary>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-slate-700">
          {Object.entries(current.statistics).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-slate-100 py-1">
              <dt className="text-slate-500">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </details>

      <div className="mt-5 flex flex-wrap gap-2">
        <button
          onClick={handleCopy}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          复制琴谱
        </button>
        <button
          onClick={handleDownload}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          下载为 .txt
        </button>
        <button
          onClick={() =>
            navigate("/tracks", {
              state: {
                file_token: fileToken,
                title: score.title,
                bpm: score.bpm,
                ticks_per_beat: score.ticks_per_beat,
                tracks: tracks ?? [],
              },
            })
          }
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          重新配置轨道
        </button>
        <button
          onClick={() => navigate("/")}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          重新搜索
        </button>
      </div>

      <p className="mt-8 text-center text-xs text-slate-400">
        本琴谱仅供个人游戏娱乐使用
      </p>
    </main>
  );
}
```

- [ ] **Step 4: Build the frontend to verify everything compiles**

Run: `cd frontend && npm run build`
Expected: build completes without errors; Vite reports the bundle output.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/VersionTabs.jsx frontend/src/components/ScoreDisplay.jsx frontend/src/pages/ScorePage.jsx
git commit -m "feat(frontend): ScorePage with version tabs, OOR highlight, copy/download"
```

---

## Task 17: README + end-to-end manual smoke

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# 原神原琴 AI 编谱

Python (FastAPI) + React full-stack tool that searches for MIDI files
across four platforms, parses them, and produces three lyre arrangements
(melody-only, simplified accompaniment, full accompaniment) ready to
play in Genshin Impact's Windsong Lyre.

## Quick start

### Backend

```bash
cd backend
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

App: http://localhost:5173

### Tests

```bash
cd backend && python -m pytest -v
```

## Architecture

- `backend/mapper/` — per-note mapping to lyre's 21 keys (no global transposition).
- `backend/arranger/` — three-version generation (chord reduction, conflict resolution, merging).
- `backend/parser/` — MIDI parsing, track classification, chord grouping.
- `backend/search/` — four platform searchers + async aggregator.
- `backend/formatter/` — PC + mobile score text generation.
- `backend/api/` — FastAPI routes (`/api/search`, `/api/parse`, `/api/upload`, `/api/generate`).
- `frontend/src/pages/` — Search → Results → TrackConfig → Score flow.

See `docs/superpowers/plans/` for the full implementation plans.
```

- [ ] **Step 2: Run the entire backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: every test passes.

- [ ] **Step 3: Build the frontend**

Run: `cd frontend && npm run build`
Expected: success.

- [ ] **Step 4: Manual end-to-end smoke (optional)**

Start backend (`uvicorn main:app --port 8000`) and frontend (`npm run dev`) in two terminals, then in the browser:
1. Open http://localhost:5173.
2. Search "canon" — even if all real platforms fail, the empty-results message must appear without errors.
3. From the Results page, click "上传本地 MIDI 文件" and pick `backend/tests/fixtures/twinkle.mid`.
4. On Track Config, leave the suggested roles, click "生成琴谱".
5. On Score page, confirm three version tabs render and the simplified version shows max_simultaneous_keys ≤ 4 in stats.

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: add project README with quick start and architecture overview"
```

---

## What's NOT in this plan

- **Optional live integration test** for spec §11.5 ("search 'canon' returns ≥1 result"). Skipped by default to keep CI offline-safe; can be added as `@pytest.mark.network`-gated in a future task.
- **Production deployment** (Docker, reverse proxy, HTTPS). Out of scope for v2.0 spec.
- **Authentication / user accounts**. The spec is single-user.
