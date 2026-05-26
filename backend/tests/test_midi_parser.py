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
