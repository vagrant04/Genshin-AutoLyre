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
