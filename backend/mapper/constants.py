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
