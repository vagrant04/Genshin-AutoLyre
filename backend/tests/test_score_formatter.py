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
