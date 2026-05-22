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
