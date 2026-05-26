# Genshin Lyre — Part 1: Foundation (Mapper + Arranger)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic, network-free core of the Genshin Lyre auto-arranger: the note-mapping engine (semitone rounding + range offset + key lookup) and the three-version arranger (chord reduction, conflict resolution, merger).

**Architecture:** Two layered, pure-Python packages. `mapper/` converts arbitrary MIDI numbers into the 21 legal lyre notes one note at a time (no global transposition). `arranger/` consumes mapped notes plus track-role labels and produces three independent versions (`melody_only`, `simplified`, `full`) per the rules in §7 of the spec.

**Tech Stack:** Python 3.11+, Pydantic v2, pytest. No network, no MIDI parsing, no FastAPI yet.

---

## File Structure

```
backend/
├── requirements.txt
├── pyproject.toml                    # pytest config + package layout
├── config.py                         # All Pydantic models + enums (shared)
├── mapper/
│   ├── __init__.py
│   ├── constants.py                  # 21-key lookup tables, octave offsets
│   └── note_mapper.py                # map_note() + map_notes()
├── arranger/
│   ├── __init__.py
│   ├── chord_reducer.py              # Column-chord reduction (root/fifth/third)
│   ├── conflict_resolver.py          # 4-key simultaneous limit (v2 only)
│   └── merger.py                     # Public entry: build_three_versions()
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Shared fixtures (sample notes, etc.)
    ├── test_mapper.py
    ├── test_chord_reducer.py
    ├── test_conflict_resolver.py
    └── test_merger.py
```

**Responsibility split:**
- `config.py` owns every shared type. Mapper and arranger import from it; nothing else lives there.
- `mapper/constants.py` is pure data (frozen dicts/sets). `note_mapper.py` is pure functions over those tables.
- `arranger/chord_reducer.py` only labels notes (`chord_position`, `is_chord_reduced`). It does not delete.
- `arranger/conflict_resolver.py` only marks `is_chord_reduced` for over-limit moments. It does not delete.
- `arranger/merger.py` is the only public entry point of this package; it composes the others and returns three `VersionScore` objects (without the `pc_score`/`mobile_score` text — that's part 3).

---

## Task 1: Project skeleton + dependencies

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/pyproject.toml`
- Create: `backend/__init__.py` (empty)
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Write `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.32.0
httpx==0.27.2
beautifulsoup4==4.12.3
lxml==5.3.0
music21==9.3.0
mido==1.3.3
python-multipart==0.0.12
aiofiles==24.1.0
pydantic==2.9.2
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 2: Write `backend/pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 3: Write `backend/tests/conftest.py`**

```python
"""Shared pytest fixtures for backend tests."""
```

- [ ] **Step 4: Create empty package init files**

Create `backend/__init__.py` and `backend/tests/__init__.py` as empty files.

- [ ] **Step 5: Install and verify pytest works**

Run: `cd backend && python -m pip install -r requirements.txt && python -m pytest -q`
Expected: `no tests ran` (exit code 5 is fine — pytest found no tests).

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "chore: scaffold backend package and pytest config"
```

---

## Task 2: Shared data models in `config.py`

**Files:**
- Create: `backend/config.py`

- [ ] **Step 1: Write `backend/config.py` (enums + models matching spec §5)**

```python
"""Shared Pydantic models and enums for the Genshin Lyre backend.

Single source of truth for all cross-module types. Importing modules must
not redefine these. Field names and types match the API contract in §10
of the requirements doc — changing them is an API-breaking change.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MusicSource(str, Enum):
    FREEMIDI = "freemidi"
    BITMIDI = "bitmidi"
    MUSESCORE = "musescore"
    BILIBILI = "bilibili"


class TrackRole(str, Enum):
    MELODY = "melody"
    ACCOMPANIMENT = "accompaniment"
    BASS = "bass"
    IGNORED = "ignored"


class ScoreVersion(str, Enum):
    MELODY_ONLY = "melody_only"
    SIMPLIFIED = "simplified"
    FULL = "full"


class ChordPosition(str, Enum):
    """Role of a note inside a column chord, used by conflict_resolver
    to decide deletion order. `OTHER` covers melody notes and any
    accompaniment note that wasn't classified as root/fifth/third."""
    ROOT = "root"
    FIFTH = "fifth"
    THIRD = "third"
    OTHER = "other"


class SearchResult(BaseModel):
    id: str
    title: str
    source: MusicSource
    source_url: str
    download_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    file_size_kb: Optional[int] = None
    track_count: Optional[int] = None
    preview_keys: Optional[str] = None
    score: float = Field(ge=0.0, le=1.0)


class TrackInfo(BaseModel):
    index: int
    name: str
    note_count: int
    pitch_range: str
    preview_keys: str
    suggested_role: TrackRole
    chord_type: str  # "chordal" | "arpeggiated" | "mixed" | "none"


class ParsedNote(BaseModel):
    midi_num: int
    start_tick: int
    duration_tick: int
    velocity: int
    track_index: int
    track_role: TrackRole


class MappedNote(BaseModel):
    original_midi: int
    mapped_midi: int
    key_pc: str
    key_mobile: str
    start_tick: int
    duration_tick: int
    track_role: TrackRole
    is_out_of_range: bool = False
    is_semitone_adjusted: bool = False
    is_chord_reduced: bool = False
    chord_position: ChordPosition = ChordPosition.OTHER


class VersionStats(BaseModel):
    total_notes: int
    melody_notes: int
    accompaniment_notes: int
    out_of_range_count: int
    semitone_count: int
    chord_reduced_count: int
    max_simultaneous_keys: int


class VersionScore(BaseModel):
    version: ScoreVersion
    version_label: str
    pc_score: str = ""        # populated by formatter (part 3)
    mobile_score: str = ""    # populated by formatter (part 3)
    notes: list[MappedNote]
    statistics: VersionStats


class LyreScore(BaseModel):
    title: str
    bpm: int
    ticks_per_beat: int
    versions: list[VersionScore]
```

- [ ] **Step 2: Verify the models import cleanly**

Run: `cd backend && python -c "from config import MappedNote, TrackRole, ScoreVersion; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "feat: add shared Pydantic models and enums"
```

---

## Task 3: Lyre key constants

**Files:**
- Create: `backend/mapper/__init__.py`
- Create: `backend/mapper/constants.py`

- [ ] **Step 1: Create `backend/mapper/__init__.py`** (empty file)

- [ ] **Step 2: Write `backend/mapper/constants.py`**

The 21 legal MIDI numbers and their PC + mobile labels per spec §6.1. The natural-semitone set `{0, 2, 4, 5, 7, 9, 11}` is used by the mapper to detect accidentals.

```python
"""Lyre key tables — single source of truth for the 21 legal notes.

Other modules MUST import these constants; they MUST NOT redefine the
mapping. Order in `LEGAL_MIDI` is ascending and is relied on by the
nearest-legal fallback in note_mapper.
"""
from __future__ import annotations

# (MIDI, PC key, mobile key) in ascending pitch order.
_KEY_TABLE: tuple[tuple[int, str, str], ...] = (
    # Low row Z X C V B N M
    (48, "Z", "-1"), (50, "X", "-2"), (52, "C", "-3"), (53, "V", "-4"),
    (55, "B", "-5"), (57, "N", "-6"), (59, "M", "-7"),
    # Middle row A S D F G H J
    (60, "A", "1"), (62, "S", "2"), (64, "D", "3"), (65, "F", "4"),
    (67, "G", "5"), (69, "H", "6"), (71, "J", "7"),
    # High row Q W E R T Y U
    (72, "Q", "+1"), (74, "W", "+2"), (76, "E", "+3"), (77, "R", "+4"),
    (79, "T", "+5"), (81, "Y", "+6"), (83, "U", "+7"),
)

MIDI_TO_PC: dict[int, str] = {m: pc for m, pc, _ in _KEY_TABLE}
MIDI_TO_MOBILE: dict[int, str] = {m: mob for m, _, mob in _KEY_TABLE}
LEGAL_MIDI: tuple[int, ...] = tuple(m for m, _, _ in _KEY_TABLE)
LEGAL_MIDI_SET: frozenset[int] = frozenset(LEGAL_MIDI)

MIDI_LOWER_BOUND: int = 48  # C3
MIDI_UPPER_BOUND: int = 83  # B5

# Semitone offsets within an octave that correspond to natural notes
# (C D E F G A B). Anything else is an accidental that must be rounded.
NATURAL_PITCH_CLASSES: frozenset[int] = frozenset({0, 2, 4, 5, 7, 9, 11})

# Spec §7.3 step three: simplified version simultaneous-key cap.
SIMPLIFIED_MAX_SIMULTANEOUS: int = 4
```

- [ ] **Step 3: Quick sanity check**

Run: `cd backend && python -c "from mapper.constants import LEGAL_MIDI, MIDI_TO_PC; assert len(LEGAL_MIDI) == 21 and MIDI_TO_PC[60] == 'A'; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/mapper/
git commit -m "feat(mapper): add lyre key constants and natural-pitch set"
```

---

## Task 4: Mapper tests (RED) — natural notes pass through

**Files:**
- Create: `backend/tests/test_mapper.py`

- [ ] **Step 1: Write the first batch of failing tests**

These are the §11.1 cases for natural-note pass-through and key-table completeness. We split tests across multiple tasks so each TDD cycle is small.

```python
"""Tests for the mapper engine. Spec §6, §7.1 step 2, §11.1."""
from __future__ import annotations

import pytest

from config import ParsedNote, TrackRole
from mapper.constants import LEGAL_MIDI, MIDI_TO_MOBILE, MIDI_TO_PC
from mapper.note_mapper import map_note, map_notes


def _note(midi: int, role: TrackRole = TrackRole.MELODY) -> ParsedNote:
    return ParsedNote(
        midi_num=midi,
        start_tick=0,
        duration_tick=240,
        velocity=80,
        track_index=0,
        track_role=role,
    )


class TestKeyTableCompleteness:
    def test_pc_table_has_all_21_keys(self):
        for midi in LEGAL_MIDI:
            assert midi in MIDI_TO_PC

    def test_mobile_table_has_all_21_keys(self):
        for midi in LEGAL_MIDI:
            assert midi in MIDI_TO_MOBILE


class TestNaturalNotesPassThrough:
    def test_c4_unchanged(self):
        result = map_note(_note(60))
        assert result.mapped_midi == 60
        assert result.key_pc == "A"
        assert result.key_mobile == "1"
        assert result.is_semitone_adjusted is False
        assert result.is_out_of_range is False

    def test_g4_unchanged(self):
        result = map_note(_note(67))
        assert result.mapped_midi == 67
        assert result.is_semitone_adjusted is False
        assert result.is_out_of_range is False
```

- [ ] **Step 2: Run tests, confirm they fail**

Run: `cd backend && python -m pytest tests/test_mapper.py -v`
Expected: import error / module-not-found for `mapper.note_mapper`.

- [ ] **Step 3: Commit (RED state)**

```bash
git add backend/tests/test_mapper.py
git commit -m "test(mapper): add natural-note pass-through and key-table tests"
```

---

## Task 5: Mapper implementation (GREEN) — minimal map_note

**Files:**
- Create: `backend/mapper/note_mapper.py`

- [ ] **Step 1: Write the minimal implementation that satisfies Task 4 tests**

We'll grow it in subsequent tasks. Per spec §8.3 the order is fixed: semitone round → range clamp → secondary check → key lookup.

```python
"""Per-note mapping engine.

Each ParsedNote is processed independently. There is NO global
transposition: see spec §1.3 constraint B. A natural note in-range
must come out unchanged.
"""
from __future__ import annotations

from typing import Iterable

from config import MappedNote, ParsedNote
from mapper.constants import (
    LEGAL_MIDI,
    LEGAL_MIDI_SET,
    MIDI_LOWER_BOUND,
    MIDI_TO_MOBILE,
    MIDI_TO_PC,
    MIDI_UPPER_BOUND,
    NATURAL_PITCH_CLASSES,
)


def _round_semitone(midi: int) -> tuple[int, bool]:
    """Round an accidental to the nearest natural pitch class within the
    same octave. Ties go to the lower natural (spec §1.3 constraint C)."""
    pc = midi % 12
    if pc in NATURAL_PITCH_CLASSES:
        return midi, False
    octave_base = midi - pc
    candidates = sorted(
        NATURAL_PITCH_CLASSES,
        key=lambda nat: (abs(nat - pc), nat),  # ties → lower natural
    )
    return octave_base + candidates[0], True


def _clamp_range(midi: int) -> tuple[int, bool]:
    """Octave-shift a single note into [C3, B5]. Local-only — does not
    inspect any other note (spec §1.3 constraint B)."""
    adjusted = False
    while midi < MIDI_LOWER_BOUND:
        midi += 12
        adjusted = True
    while midi > MIDI_UPPER_BOUND:
        midi -= 12
        adjusted = True
    return midi, adjusted


def _snap_to_legal(midi: int) -> int:
    """Final guard: if rounding+clamp still produced an illegal MIDI
    (extreme edge cases at the range boundary), pick the closest legal
    note."""
    if midi in LEGAL_MIDI_SET:
        return midi
    return min(LEGAL_MIDI, key=lambda legal: abs(legal - midi))


def map_note(note: ParsedNote) -> MappedNote:
    rounded, semitone_adjusted = _round_semitone(note.midi_num)
    clamped, out_of_range = _clamp_range(rounded)
    final = _snap_to_legal(clamped)
    return MappedNote(
        original_midi=note.midi_num,
        mapped_midi=final,
        key_pc=MIDI_TO_PC[final],
        key_mobile=MIDI_TO_MOBILE[final],
        start_tick=note.start_tick,
        duration_tick=note.duration_tick,
        track_role=note.track_role,
        is_out_of_range=out_of_range,
        is_semitone_adjusted=semitone_adjusted,
    )


def map_notes(notes: Iterable[ParsedNote]) -> list[MappedNote]:
    """Map a batch of notes. Each note is processed independently — no
    note's mapping may depend on another note's value."""
    return [map_note(n) for n in notes]
```

- [ ] **Step 2: Run tests to verify GREEN**

Run: `cd backend && python -m pytest tests/test_mapper.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/mapper/note_mapper.py
git commit -m "feat(mapper): map_note with semitone rounding and range clamp"
```

---

## Task 6: Mapper tests — semitone rounding

**Files:**
- Modify: `backend/tests/test_mapper.py` (append)

- [ ] **Step 1: Append the semitone-rounding tests from spec §11.1**

Add this class at the end of `backend/tests/test_mapper.py`:

```python
class TestSemitoneRounding:
    def test_f_sharp_4_rounds_down_to_f4(self):
        # Tie-break: F#4 (66) is equidistant to F4 (65) and G4 (67); take lower.
        result = map_note(_note(66))
        assert result.mapped_midi == 65
        assert result.key_pc == "F"
        assert result.is_semitone_adjusted is True

    def test_b_flat_4_rounds_down_to_a4(self):
        # Bb4 (70) → A4 (69), taking the lower natural per the tie rule.
        result = map_note(_note(70))
        assert result.mapped_midi == 69
        assert result.key_pc == "H"
        assert result.is_semitone_adjusted is True

    def test_c_sharp_4_rounds_to_c4(self):
        # C#4 (61) → C4 (60); D4 is 2 semitones away, C4 is 1.
        result = map_note(_note(61))
        assert result.mapped_midi == 60
        assert result.key_pc == "A"
        assert result.is_semitone_adjusted is True

    def test_natural_note_is_not_marked_adjusted(self):
        result = map_note(_note(64))  # E4
        assert result.is_semitone_adjusted is False
```

- [ ] **Step 2: Run tests, verify they pass**

Run: `cd backend && python -m pytest tests/test_mapper.py -v`
Expected: all 8 tests PASS (the existing `_round_semitone` already handles these — no implementation change needed).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mapper.py
git commit -m "test(mapper): cover semitone rounding tie-break rule"
```

---

## Task 7: Mapper tests — out-of-range octave shift

**Files:**
- Modify: `backend/tests/test_mapper.py` (append)

- [ ] **Step 1: Append the range-shift tests from spec §11.1**

```python
class TestOutOfRangeShift:
    def test_c2_lifted_to_c3(self):
        # MIDI 36 (C2) → 48 (C3), +12.
        result = map_note(_note(36))
        assert result.mapped_midi == 48
        assert result.key_pc == "Z"
        assert result.is_out_of_range is True

    def test_b6_dropped_to_b5(self):
        # MIDI 95 (B6) → 83 (B5), -12.
        result = map_note(_note(95))
        assert result.mapped_midi == 83
        assert result.key_pc == "U"
        assert result.is_out_of_range is True

    def test_extremely_low_note_lifts_repeatedly(self):
        # MIDI 24 (C1) needs +12 twice → 48 (C3).
        result = map_note(_note(24))
        assert result.mapped_midi == 48
        assert result.is_out_of_range is True

    def test_extremely_high_note_drops_repeatedly(self):
        # MIDI 107 (B7) needs -12 twice → 83 (B5).
        result = map_note(_note(107))
        assert result.mapped_midi == 83
        assert result.is_out_of_range is True
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_mapper.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mapper.py
git commit -m "test(mapper): cover out-of-range octave shifting"
```

---

## Task 8: Mapper tests — independence (no global transposition)

**Files:**
- Modify: `backend/tests/test_mapper.py` (append)

- [ ] **Step 1: Append the independence tests from spec §11.1**

This is the most important correctness test in the project — it locks in constraint B.

```python
class TestNoGlobalTransposition:
    def test_each_note_processed_independently(self):
        # 5 notes: 2 out of range, 3 inside. The 3 inside notes must
        # come out unchanged regardless of the others.
        notes = [
            _note(36),   # C2 — out of range, must shift to 48
            _note(60),   # C4 — in range, unchanged
            _note(67),   # G4 — in range, unchanged
            _note(95),   # B6 — out of range, must shift to 83
            _note(72),   # C5 — in range, unchanged
        ]
        result = map_notes(notes)

        assert result[0].mapped_midi == 48 and result[0].is_out_of_range
        assert result[1].mapped_midi == 60 and not result[1].is_out_of_range
        assert result[2].mapped_midi == 67 and not result[2].is_out_of_range
        assert result[3].mapped_midi == 83 and result[3].is_out_of_range
        assert result[4].mapped_midi == 72 and not result[4].is_out_of_range

    def test_one_outlier_does_not_drag_others(self):
        # If we naively transposed the whole set down to fit MIDI 95,
        # MIDI 60 would become 48. We assert it stays at 60.
        notes = [_note(60), _note(95)]
        result = map_notes(notes)
        assert result[0].mapped_midi == 60
        assert result[1].mapped_midi == 83

    def test_track_role_is_preserved(self):
        result = map_note(_note(60, role=TrackRole.ACCOMPANIMENT))
        assert result.track_role == TrackRole.ACCOMPANIMENT
```

- [ ] **Step 2: Run tests**

Run: `cd backend && python -m pytest tests/test_mapper.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_mapper.py
git commit -m "test(mapper): assert per-note independence (no global transposition)"
```

---

## Task 9: Chord-reducer tests (RED)

**Files:**
- Create: `backend/arranger/__init__.py` (empty)
- Create: `backend/tests/test_chord_reducer.py`

- [ ] **Step 1: Create empty package init**

Create `backend/arranger/__init__.py` as an empty file.

- [ ] **Step 2: Write failing tests for `reduce_simultaneous_chord`**

The reducer takes a list of accompaniment `MappedNote`s that are simultaneous (same start_tick, give or take), and returns the same list with `chord_position` and `is_chord_reduced` set per spec §7.3 step one + §8.4.1.

```python
"""Tests for arranger.chord_reducer. Spec §7.3 step 1, §8.4.1, §11.2."""
from __future__ import annotations

import pytest

from config import ChordPosition, MappedNote, TrackRole
from arranger.chord_reducer import reduce_simultaneous_chord


def _mapped(midi: int, key_pc: str, key_mobile: str) -> MappedNote:
    return MappedNote(
        original_midi=midi,
        mapped_midi=midi,
        key_pc=key_pc,
        key_mobile=key_mobile,
        start_tick=0,
        duration_tick=480,
        track_role=TrackRole.ACCOMPANIMENT,
    )


class TestColumnChordReduction:
    def test_three_note_major_chord_keeps_root_and_fifth(self):
        # C major: C4, E4, G4 — root + fifth retained, third may be kept too.
        c, e, g = _mapped(60, "A", "1"), _mapped(64, "D", "3"), _mapped(67, "G", "5")
        result = reduce_simultaneous_chord([c, e, g])

        kept = [n for n in result if not n.is_chord_reduced]
        kept_midi = {n.mapped_midi for n in kept}
        assert 60 in kept_midi  # root must survive
        assert 67 in kept_midi  # fifth must survive

        positions = {n.mapped_midi: n.chord_position for n in result}
        assert positions[60] == ChordPosition.ROOT
        assert positions[67] == ChordPosition.FIFTH
        assert positions[64] == ChordPosition.THIRD

    def test_four_note_chord_drops_extras(self):
        # C, E, G, B — keep ≤3, drop one. Root + fifth survive.
        c = _mapped(60, "A", "1")
        e = _mapped(64, "D", "3")
        g = _mapped(67, "G", "5")
        b = _mapped(71, "J", "7")
        result = reduce_simultaneous_chord([c, e, g, b])

        kept = [n for n in result if not n.is_chord_reduced]
        kept_midi = {n.mapped_midi for n in kept}
        assert 60 in kept_midi
        assert 67 in kept_midi
        assert len(kept) <= 3

        # B (the non-root, non-fifth, non-third extra) must be reduced.
        b_note = next(n for n in result if n.mapped_midi == 71)
        assert b_note.is_chord_reduced is True
        assert b_note.chord_position == ChordPosition.OTHER

    def test_single_note_passes_through(self):
        only = _mapped(60, "A", "1")
        result = reduce_simultaneous_chord([only])
        assert len(result) == 1
        assert result[0].is_chord_reduced is False
        assert result[0].chord_position == ChordPosition.ROOT

    def test_two_note_chord_keeps_both(self):
        c, g = _mapped(60, "A", "1"), _mapped(67, "G", "5")
        result = reduce_simultaneous_chord([c, g])
        assert all(n.is_chord_reduced is False for n in result)
        positions = {n.mapped_midi: n.chord_position for n in result}
        assert positions[60] == ChordPosition.ROOT
        assert positions[67] == ChordPosition.FIFTH
```

- [ ] **Step 3: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_chord_reducer.py -v`
Expected: import error.

- [ ] **Step 4: Commit (RED)**

```bash
git add backend/arranger/__init__.py backend/tests/test_chord_reducer.py
git commit -m "test(arranger): add chord reducer specification tests"
```

---

## Task 10: Chord-reducer implementation (GREEN)

**Files:**
- Create: `backend/arranger/chord_reducer.py`

- [ ] **Step 1: Write the reducer**

```python
"""Column-chord reduction for the simplified version.

Given a set of simultaneous accompaniment notes, label each by chord
position (root / fifth / third / other) and mark the ones that should
be dropped. Per spec §8.4.1: keep the root, the closest fifth above
root, and the closest third above root, up to 3 notes total.

This module ONLY labels — it never deletes from the list. Downstream
consumers filter on `is_chord_reduced`.
"""
from __future__ import annotations

from config import ChordPosition, MappedNote


def reduce_simultaneous_chord(group: list[MappedNote]) -> list[MappedNote]:
    """Label and reduce a group of simultaneous accompaniment notes.

    Returned list is the same length as input; each note has
    `chord_position` set and `is_chord_reduced` set to True for notes
    that should not appear in the simplified output.
    """
    if not group:
        return []
    if len(group) == 1:
        sole = group[0].model_copy(update={"chord_position": ChordPosition.ROOT})
        return [sole]

    # Sort ascending by mapped_midi so the lowest note is the root.
    by_pitch = sorted(group, key=lambda n: n.mapped_midi)
    root = by_pitch[0]

    # Closest fifth above root: prefer +7 semitones, fall back to nearest
    # remaining note that is at least a perfect fourth above root.
    rest = list(by_pitch[1:])
    fifth = _pick_closest_to(rest, target=root.mapped_midi + 7)
    if fifth is not None:
        rest.remove(fifth)

    # Closest third above root: prefer +4 (major) then +3 (minor).
    third = _pick_closest_to(rest, target=root.mapped_midi + 4)
    if third is None:
        third = _pick_closest_to(rest, target=root.mapped_midi + 3)
    if third is not None:
        rest.remove(third)

    kept_ids = {id(root)}
    if fifth is not None:
        kept_ids.add(id(fifth))
    if third is not None:
        kept_ids.add(id(third))

    output: list[MappedNote] = []
    for note in group:
        if note is root:
            output.append(note.model_copy(update={"chord_position": ChordPosition.ROOT}))
        elif fifth is not None and note is fifth:
            output.append(note.model_copy(update={"chord_position": ChordPosition.FIFTH}))
        elif third is not None and note is third:
            output.append(note.model_copy(update={"chord_position": ChordPosition.THIRD}))
        else:
            output.append(note.model_copy(update={
                "chord_position": ChordPosition.OTHER,
                "is_chord_reduced": True,
            }))
    return output


def _pick_closest_to(candidates: list[MappedNote], target: int) -> MappedNote | None:
    if not candidates:
        return None
    return min(candidates, key=lambda n: abs(n.mapped_midi - target))
```

- [ ] **Step 2: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_chord_reducer.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/arranger/chord_reducer.py
git commit -m "feat(arranger): chord_reducer labels root/fifth/third and marks extras"
```

---

## Task 11: Conflict-resolver tests (RED)

**Files:**
- Create: `backend/tests/test_conflict_resolver.py`

- [ ] **Step 1: Write failing tests for `resolve_simultaneous_limit`**

Per spec §7.3 step three + §8.4.3. Input is a fully merged note list (melody + already-labeled accompaniment); output is the same list with extra notes marked `is_chord_reduced` so that no instant has more than 4 simultaneous keys (unless melody alone exceeds 4).

```python
"""Tests for arranger.conflict_resolver. Spec §7.3 step 3, §8.4.3, §11.3."""
from __future__ import annotations

from config import ChordPosition, MappedNote, TrackRole
from arranger.conflict_resolver import resolve_simultaneous_limit


def _note(
    midi: int,
    role: TrackRole,
    *,
    start: int = 0,
    duration: int = 480,
    chord_position: ChordPosition = ChordPosition.OTHER,
) -> MappedNote:
    return MappedNote(
        original_midi=midi,
        mapped_midi=midi,
        key_pc="A",
        key_mobile="1",
        start_tick=start,
        duration_tick=duration,
        track_role=role,
        chord_position=chord_position,
    )


def _kept(notes: list[MappedNote]) -> list[MappedNote]:
    return [n for n in notes if not n.is_chord_reduced]


def _max_simultaneous(notes: list[MappedNote]) -> int:
    """Brute-force count of max simultaneous kept notes across all start ticks."""
    kept = _kept(notes)
    if not kept:
        return 0
    return max(
        sum(1 for n in kept if n.start_tick <= t < n.start_tick + n.duration_tick)
        for t in {n.start_tick for n in kept}
    )


class TestSimultaneousLimit:
    def test_three_melody_three_accompaniment_drops_to_four(self):
        # 3 melody + 3 accompaniment = 6 simultaneous. Must reduce to ≤4 by
        # cutting accompaniment (third → fifth → root).
        notes = [
            _note(60, TrackRole.MELODY),
            _note(64, TrackRole.MELODY),
            _note(67, TrackRole.MELODY),
            _note(48, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.ROOT),
            _note(52, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.THIRD),
            _note(55, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.FIFTH),
        ]
        result = resolve_simultaneous_limit(notes)
        assert _max_simultaneous(result) <= 4

        # All melody must survive.
        kept_melody = [n for n in _kept(result) if n.track_role == TrackRole.MELODY]
        assert len(kept_melody) == 3

        # The third was the first to go.
        third_note = next(n for n in result if n.chord_position == ChordPosition.THIRD)
        assert third_note.is_chord_reduced is True

    def test_four_melody_two_accompaniment_drops_all_accompaniment(self):
        notes = [
            _note(60, TrackRole.MELODY),
            _note(62, TrackRole.MELODY),
            _note(64, TrackRole.MELODY),
            _note(65, TrackRole.MELODY),
            _note(48, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.ROOT),
            _note(55, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.FIFTH),
        ]
        result = resolve_simultaneous_limit(notes)

        kept_melody = [n for n in _kept(result) if n.track_role == TrackRole.MELODY]
        kept_accomp = [n for n in _kept(result) if n.track_role == TrackRole.ACCOMPANIMENT]
        assert len(kept_melody) == 4
        assert len(kept_accomp) == 0
        assert _max_simultaneous(result) == 4

    def test_five_melody_notes_all_survive(self):
        # Pathological: melody itself has 5 simultaneous notes. Spec says
        # melody is never cut, so we accept >4 here.
        notes = [_note(60 + i, TrackRole.MELODY) for i in (0, 2, 4, 5, 7)]
        result = resolve_simultaneous_limit(notes)
        kept_melody = [n for n in _kept(result) if n.track_role == TrackRole.MELODY]
        assert len(kept_melody) == 5

    def test_four_total_notes_unchanged(self):
        # Already at the limit — nothing should be marked.
        notes = [
            _note(60, TrackRole.MELODY),
            _note(64, TrackRole.MELODY),
            _note(48, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.ROOT),
            _note(55, TrackRole.ACCOMPANIMENT, chord_position=ChordPosition.FIFTH),
        ]
        result = resolve_simultaneous_limit(notes)
        assert all(n.is_chord_reduced is False for n in result)

    def test_non_overlapping_notes_unaffected(self):
        # Two groups of 3 simultaneous, but they don't overlap in time.
        notes = [
            _note(60, TrackRole.MELODY, start=0, duration=240),
            _note(64, TrackRole.MELODY, start=0, duration=240),
            _note(48, TrackRole.ACCOMPANIMENT, start=0, duration=240,
                  chord_position=ChordPosition.ROOT),
            _note(60, TrackRole.MELODY, start=480, duration=240),
            _note(64, TrackRole.MELODY, start=480, duration=240),
            _note(48, TrackRole.ACCOMPANIMENT, start=480, duration=240,
                  chord_position=ChordPosition.ROOT),
        ]
        result = resolve_simultaneous_limit(notes)
        assert all(n.is_chord_reduced is False for n in result)
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_conflict_resolver.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_conflict_resolver.py
git commit -m "test(arranger): add conflict resolver simultaneous-limit tests"
```

---

## Task 12: Conflict-resolver implementation (GREEN)

**Files:**
- Create: `backend/arranger/conflict_resolver.py`

- [ ] **Step 1: Write the resolver**

```python
"""Enforce the 4-key simultaneous limit for the simplified version.

Spec §7.3 step 3 / §8.4.3:
  - At every start_tick of every note, count how many notes are sounding.
  - If >4, drop accompaniment notes (NEVER melody) in priority order:
    third → fifth → root → other.
  - If melody alone is already >4, leave it: melody is never cut.

This module mutates `is_chord_reduced` only. It does not delete entries
from the list.
"""
from __future__ import annotations

from config import ChordPosition, MappedNote, TrackRole
from mapper.constants import SIMPLIFIED_MAX_SIMULTANEOUS

# Lower priority value = removed first.
_REMOVAL_PRIORITY: dict[ChordPosition, int] = {
    ChordPosition.OTHER: 0,
    ChordPosition.THIRD: 1,
    ChordPosition.FIFTH: 2,
    ChordPosition.ROOT: 3,
}


def resolve_simultaneous_limit(notes: list[MappedNote]) -> list[MappedNote]:
    """Mark accompaniment notes as `is_chord_reduced` until no instant
    has more than 4 simultaneous *kept* notes (or only melody remains)."""
    # Work on copies so we don't mutate caller-owned objects.
    working: list[MappedNote] = [n.model_copy() for n in notes]

    # Check at every distinct start_tick: that's where note counts change.
    distinct_starts = sorted({n.start_tick for n in working})

    for tick in distinct_starts:
        sounding_indices = [
            i for i, n in enumerate(working)
            if not n.is_chord_reduced
            and n.start_tick <= tick < n.start_tick + n.duration_tick
        ]
        while len(sounding_indices) > SIMPLIFIED_MAX_SIMULTANEOUS:
            accompaniment_indices = [
                i for i in sounding_indices
                if working[i].track_role == TrackRole.ACCOMPANIMENT
            ]
            if not accompaniment_indices:
                # Pure-melody overload — spec says leave it.
                break
            # Pick the accompaniment note with the lowest removal priority.
            victim = min(
                accompaniment_indices,
                key=lambda i: (
                    _REMOVAL_PRIORITY[working[i].chord_position],
                    working[i].mapped_midi,
                ),
            )
            working[victim] = working[victim].model_copy(
                update={"is_chord_reduced": True}
            )
            sounding_indices = [
                i for i, n in enumerate(working)
                if not n.is_chord_reduced
                and n.start_tick <= tick < n.start_tick + n.duration_tick
            ]
    return working
```

- [ ] **Step 2: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_conflict_resolver.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/arranger/conflict_resolver.py
git commit -m "feat(arranger): conflict resolver enforces 4-key simultaneous limit"
```

---

## Task 13: Merger tests (RED)

**Files:**
- Create: `backend/tests/test_merger.py`

- [ ] **Step 1: Write failing tests covering all three versions per spec §11.4**

The merger is the public entry point of the arranger package. Signature:
```
build_three_versions(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
    chord_groups: list[list[MappedNote]],  # accompaniment grouped into simultaneous chords
) -> dict[ScoreVersion, VersionScore]
```

- The caller is responsible for grouping accompaniment notes into chord-groups (we'll do that grouping inside the merger for now using a simple "same start_tick within tolerance" rule, since the spec defines it).
- For tests, we'll pre-group manually.

```python
"""Tests for arranger.merger.build_three_versions. Spec §7, §11.4."""
from __future__ import annotations

from config import ChordPosition, MappedNote, ScoreVersion, TrackRole
from arranger.merger import build_three_versions


def _n(
    midi: int,
    role: TrackRole,
    *,
    start: int = 0,
    duration: int = 480,
) -> MappedNote:
    return MappedNote(
        original_midi=midi,
        mapped_midi=midi,
        key_pc="A",
        key_mobile="1",
        start_tick=start,
        duration_tick=duration,
        track_role=role,
    )


def _kept(notes):
    return [n for n in notes if not n.is_chord_reduced]


class TestMelodyOnlyVersion:
    def test_excludes_all_accompaniment(self):
        melody = [_n(60, TrackRole.MELODY, start=0), _n(62, TrackRole.MELODY, start=480)]
        accomp = [_n(48, TrackRole.ACCOMPANIMENT, start=0)]
        result = build_three_versions(melody, accomp, chord_groups=[[accomp[0]]])
        v1 = result[ScoreVersion.MELODY_ONLY]
        kept = _kept(v1.notes)
        assert all(n.track_role == TrackRole.MELODY for n in kept)
        assert len(kept) == 2


class TestSimplifiedVersion:
    def test_max_simultaneous_within_limit(self):
        # 3 melody + 3 accompaniment all at tick 0 → must be ≤ 4 after merge.
        melody = [
            _n(60, TrackRole.MELODY, start=0),
            _n(64, TrackRole.MELODY, start=0),
            _n(67, TrackRole.MELODY, start=0),
        ]
        accomp = [
            _n(48, TrackRole.ACCOMPANIMENT, start=0),
            _n(52, TrackRole.ACCOMPANIMENT, start=0),
            _n(55, TrackRole.ACCOMPANIMENT, start=0),
        ]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v2 = result[ScoreVersion.SIMPLIFIED]
        assert v2.statistics.max_simultaneous_keys <= 4

    def test_melody_count_preserved_under_pressure(self):
        melody = [_n(60 + i * 2, TrackRole.MELODY, start=0) for i in range(3)]
        accomp = [_n(48 + i * 2, TrackRole.ACCOMPANIMENT, start=0) for i in range(3)]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v2 = result[ScoreVersion.SIMPLIFIED]
        assert v2.statistics.melody_notes == 3


class TestFullVersion:
    def test_all_notes_kept(self):
        melody = [_n(60, TrackRole.MELODY, start=0), _n(62, TrackRole.MELODY, start=480)]
        accomp = [
            _n(48, TrackRole.ACCOMPANIMENT, start=0),
            _n(52, TrackRole.ACCOMPANIMENT, start=0),
            _n(55, TrackRole.ACCOMPANIMENT, start=0),
            _n(48, TrackRole.ACCOMPANIMENT, start=480),
        ]
        result = build_three_versions(melody, accomp, chord_groups=[accomp[:3], [accomp[3]]])
        v3 = result[ScoreVersion.FULL]
        kept = _kept(v3.notes)
        assert len(kept) == len(melody) + len(accomp)
        assert v3.statistics.total_notes == len(kept)
        # Stats invariant from spec §11.4.
        assert (
            v3.statistics.total_notes
            == v3.statistics.melody_notes + v3.statistics.accompaniment_notes
        )

    def test_full_allows_more_than_four_simultaneous(self):
        # 3 melody + 3 accompaniment all at tick 0 → full version keeps 6.
        melody = [_n(60 + i, TrackRole.MELODY, start=0) for i in (0, 2, 4)]
        accomp = [_n(48 + i, TrackRole.ACCOMPANIMENT, start=0) for i in (0, 4, 7)]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v3 = result[ScoreVersion.FULL]
        assert v3.statistics.max_simultaneous_keys == 6


class TestVersionLabels:
    def test_three_versions_returned(self):
        result = build_three_versions([], [], chord_groups=[])
        assert set(result.keys()) == {
            ScoreVersion.MELODY_ONLY,
            ScoreVersion.SIMPLIFIED,
            ScoreVersion.FULL,
        }

    def test_chinese_labels(self):
        result = build_three_versions([], [], chord_groups=[])
        assert result[ScoreVersion.MELODY_ONLY].version_label == "纯旋律版"
        assert result[ScoreVersion.SIMPLIFIED].version_label == "简化伴奏版"
        assert result[ScoreVersion.FULL].version_label == "完整伴奏版"
```

- [ ] **Step 2: Run tests, confirm RED**

Run: `cd backend && python -m pytest tests/test_merger.py -v`
Expected: import error.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_merger.py
git commit -m "test(arranger): add merger three-version specification tests"
```

---

## Task 14: Merger implementation (GREEN)

**Files:**
- Create: `backend/arranger/merger.py`

- [ ] **Step 1: Write `build_three_versions`**

```python
"""Public arranger entry point.

Given the per-track MappedNote lists and the accompaniment chord
groupings the parser detected, produce three independent VersionScore
objects (melody_only / simplified / full) per spec §7.

Note: pc_score / mobile_score text is filled in later by the formatter
module (part 3 of the project). Here we only compute the note lists
and statistics.
"""
from __future__ import annotations

from config import (
    ChordPosition,
    MappedNote,
    ScoreVersion,
    TrackRole,
    VersionScore,
    VersionStats,
)
from arranger.chord_reducer import reduce_simultaneous_chord
from arranger.conflict_resolver import resolve_simultaneous_limit


_VERSION_LABELS: dict[ScoreVersion, str] = {
    ScoreVersion.MELODY_ONLY: "纯旋律版",
    ScoreVersion.SIMPLIFIED: "简化伴奏版",
    ScoreVersion.FULL: "完整伴奏版",
}


def build_three_versions(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
    chord_groups: list[list[MappedNote]],
) -> dict[ScoreVersion, VersionScore]:
    """Produce the three versions.

    `chord_groups` is the parser's grouping of `accompaniment_notes`
    into simultaneous-chord buckets (each inner list has notes whose
    start_tick differs by ≤ 30 ticks per spec §7.3 step 1). The merger
    uses these groups for the simplified version's chord reduction.
    """
    melody_sorted = sorted(melody_notes, key=lambda n: n.start_tick)

    return {
        ScoreVersion.MELODY_ONLY: _build_melody_only(melody_sorted),
        ScoreVersion.SIMPLIFIED: _build_simplified(
            melody_sorted, accompaniment_notes, chord_groups
        ),
        ScoreVersion.FULL: _build_full(melody_sorted, accompaniment_notes),
    }


def _build_melody_only(melody_notes: list[MappedNote]) -> VersionScore:
    notes = [n.model_copy() for n in melody_notes]
    return VersionScore(
        version=ScoreVersion.MELODY_ONLY,
        version_label=_VERSION_LABELS[ScoreVersion.MELODY_ONLY],
        notes=notes,
        statistics=_compute_stats(notes),
    )


def _build_simplified(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
    chord_groups: list[list[MappedNote]],
) -> VersionScore:
    # Step 1 of §7.3: chord-reduce each accompaniment group.
    reduced_accomp: list[MappedNote] = []
    grouped_ids = set()
    for group in chord_groups:
        for note in group:
            grouped_ids.add(id(note))
        reduced_accomp.extend(reduce_simultaneous_chord(group))

    # Any accompaniment note that wasn't in a group (e.g. arpeggio singles)
    # passes through untouched.
    for note in accompaniment_notes:
        if id(note) not in grouped_ids:
            reduced_accomp.append(
                note.model_copy(update={"chord_position": ChordPosition.OTHER})
            )

    # Step 2: merge melody + reduced accompaniment, sort.
    merged = sorted(
        [n.model_copy() for n in melody_notes] + reduced_accomp,
        key=lambda n: (n.start_tick, n.track_role.value),
    )

    # Step 3: enforce 4-key simultaneous limit (skips already-reduced notes).
    resolved = resolve_simultaneous_limit(merged)

    return VersionScore(
        version=ScoreVersion.SIMPLIFIED,
        version_label=_VERSION_LABELS[ScoreVersion.SIMPLIFIED],
        notes=resolved,
        statistics=_compute_stats(resolved),
    )


def _build_full(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
) -> VersionScore:
    merged = sorted(
        [n.model_copy() for n in melody_notes]
        + [n.model_copy() for n in accompaniment_notes],
        key=lambda n: (n.start_tick, n.track_role.value),
    )
    return VersionScore(
        version=ScoreVersion.FULL,
        version_label=_VERSION_LABELS[ScoreVersion.FULL],
        notes=merged,
        statistics=_compute_stats(merged),
    )


def _compute_stats(notes: list[MappedNote]) -> VersionStats:
    kept = [n for n in notes if not n.is_chord_reduced]
    melody = [n for n in kept if n.track_role == TrackRole.MELODY]
    accomp = [n for n in kept if n.track_role == TrackRole.ACCOMPANIMENT]
    return VersionStats(
        total_notes=len(kept),
        melody_notes=len(melody),
        accompaniment_notes=len(accomp),
        out_of_range_count=sum(1 for n in kept if n.is_out_of_range),
        semitone_count=sum(1 for n in kept if n.is_semitone_adjusted),
        chord_reduced_count=sum(1 for n in notes if n.is_chord_reduced),
        max_simultaneous_keys=_max_simultaneous(kept),
    )


def _max_simultaneous(notes: list[MappedNote]) -> int:
    if not notes:
        return 0
    distinct_starts = {n.start_tick for n in notes}
    return max(
        sum(
            1
            for n in notes
            if n.start_tick <= tick < n.start_tick + n.duration_tick
        )
        for tick in distinct_starts
    )
```

- [ ] **Step 2: Run tests, verify GREEN**

Run: `cd backend && python -m pytest tests/test_merger.py -v`
Expected: all tests PASS.

- [ ] **Step 3: Run the entire test suite to confirm no regressions**

Run: `cd backend && python -m pytest -v`
Expected: all tests across `test_mapper.py`, `test_chord_reducer.py`, `test_conflict_resolver.py`, `test_merger.py` PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/arranger/merger.py
git commit -m "feat(arranger): build_three_versions composes the three lyre versions"
```

---

## Task 15: Final foundation review

**Files:**
- None (verification only).

- [ ] **Step 1: Re-run the full test suite with verbose output**

Run: `cd backend && python -m pytest -v --tb=short`
Expected: 100% pass.

- [ ] **Step 2: Confirm package can be imported as a whole**

Run: `cd backend && python -c "from arranger.merger import build_three_versions; from mapper.note_mapper import map_notes; print('foundation ready')"`
Expected: `foundation ready`

- [ ] **Step 3: Tag the commit history (informational)**

```bash
git log --oneline | head -20
```

This part is now complete. Subsequent plans (part 2: parser + downloader, part 3: formatter + API + frontend) will build on top of these stable, tested modules.

---

## What's NOT in this plan (intentionally deferred)

- **MIDI parsing & track classification** — needs `music21`/`mido` and real MIDI files; deferred to part 2.
- **Search aggregator & 4 platform searchers** — network-dependent; part 2.
- **Score formatter** (PC/mobile text generation) — needs design decisions about line-length, hold markers, and chord-bracket grouping rules (spec §8.5 has the rules; will be a small standalone task); part 3.
- **FastAPI routes & frontend** — part 3.

Splitting at this seam keeps part 1 fully unit-testable, network-free, and parser-free. Every requirement in spec §6, §7, §11.1, §11.2, §11.3, §11.4 is covered here.
