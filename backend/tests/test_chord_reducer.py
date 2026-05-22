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
