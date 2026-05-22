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
