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
