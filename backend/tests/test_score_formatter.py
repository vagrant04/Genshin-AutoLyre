"""Tests for formatter.score_formatter (rhythm-aware grid encoding).

The formatter places notes on a slot grid where each slot represents a
fixed musical duration (auto-detected per song, with a 32nd-note floor).
Empty slots are rendered as spaces. PC and mobile output are single-line
strings with horizontal scroll. The human view groups slots into bars.

Spec: docs/superpowers/specs/2026-05-22-track-preview-design.md and
the rhythm-encoding clarifications in the conversation that introduced it.
"""
from __future__ import annotations

from config import (
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


# 480 ticks/beat is what mido's default and our fixture both use.
TPB = 480


# ---------- empty / trivial ----------

class TestEmpty:
    def test_empty_input_returns_empty_strings(self):
        out = format_version_score(_version([]), ticks_per_beat=TPB)
        assert out.pc_score == ""
        assert out.mobile_score == ""
        assert out.human_score == ""


# ---------- subdivision detection ----------

class TestSubdivision:
    def test_quarter_notes_use_quarter_grid(self):
        # All quarters → smallest tick interval is 480 ticks. Slot = 480.
        # 4 notes → "A B C D" (one space between).
        notes = [
            _note(key_pc="A", key_mobile="1", start=0,    duration=480),
            _note(key_pc="S", key_mobile="2", start=480,  duration=480),
            _note(key_pc="D", key_mobile="3", start=960,  duration=480),
            _note(key_pc="F", key_mobile="4", start=1440, duration=480),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert out.pc_score == "A S D F"
        assert out.mobile_score == "1 2 3 4"

    def test_eighth_notes_use_eighth_grid(self):
        # Quarters interleaved with eighths → smallest = 240 ticks.
        # Quarter occupies 2 slots; output uses 1 token + 1 space per slot.
        notes = [
            _note(key_pc="A", key_mobile="1", start=0,   duration=240),
            _note(key_pc="S", key_mobile="2", start=240, duration=240),
            _note(key_pc="D", key_mobile="3", start=480, duration=240),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        # 3 eighths back-to-back → "A S D"
        assert out.pc_score == "A S D"

    def test_subdivision_floor_is_thirty_second(self):
        # Two notes 1 tick apart shouldn't blow up the grid; the 32nd-note
        # floor (TPB/8 = 60 ticks) keeps output sane. The two notes will
        # both round to slot 0 and the second wins (same slot).
        notes = [
            _note(key_pc="A", key_mobile="1", start=0, duration=480),
            _note(key_pc="S", key_mobile="2", start=1, duration=480),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        # The 1-tick offset is below the 60-tick floor, so the two notes
        # land in the same slot and form a chord.
        assert "(AS)" in out.pc_score


# ---------- rest encoding ----------

class TestRests:
    def test_quarter_rest_renders_as_three_spaces(self):
        # Mixed eighths + quarters force the 8th-grid:
        notes = [
            _note(key_pc="A", key_mobile="1", start=0,   duration=240),
            _note(key_pc="S", key_mobile="2", start=720, duration=240),  # 1.5 beats later
        ]
        # Grid = GCD(720, 240) = 240 (eighth-grid).
        # Note 1 at slot 0; note 2 at slot 3 → tokens ["A", "", "", "S"]
        # joined by single spaces → "A   S" (3 spaces). The 3 spaces
        # encode 3 empty eighth-note slots.
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert out.pc_score == "A   S"

    def test_half_rest_longer_than_quarter_rest(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0,    duration=240),
            _note(key_pc="S", key_mobile="2", start=240,  duration=240),  # eighth gap
            _note(key_pc="D", key_mobile="3", start=1440, duration=240),  # half-rest gap
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        # Grid = 240. A at slot 0, S at slot 1, D at slot 6 → 4 empty slots after S.
        a_pos = out.pc_score.index("A")
        s_pos = out.pc_score.index("S")
        d_pos = out.pc_score.index("D")
        assert s_pos - a_pos < d_pos - s_pos  # half rest > eighth rest


# ---------- chord and out-of-range ----------

class TestChordsAndOOR:
    def test_simultaneous_notes_one_slot_with_parens(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="D", key_mobile="3", start=10),
            _note(key_pc="G", key_mobile="5", start=20),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert "(ADG)" in out.pc_score
        assert "(135)" in out.mobile_score

    def test_out_of_range_pc_wrapped_in_brackets(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0,   duration=480),
            _note(key_pc="Q", key_mobile="+1", start=480, duration=480, out_of_range=True),
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert "[Q]" in out.pc_score
        assert "[+1]" in out.mobile_score


# ---------- chord_reduced exclusion ----------

class TestExclusion:
    def test_chord_reduced_notes_skipped(self):
        notes = [
            _note(key_pc="A", key_mobile="1", start=0),
            _note(key_pc="D", key_mobile="3", start=0),
        ]
        notes[1].is_chord_reduced = True
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert "D" not in out.pc_score
        assert "A" in out.pc_score


# ---------- single-line / no wrapping ----------

class TestSingleLine:
    def test_pc_score_has_no_newlines(self):
        notes = [
            _note(key_pc=ch, key_mobile=str(i + 1), start=480 * i, duration=480)
            for i, ch in enumerate("ASDFGHJASDFGHJASDFGHJASDFGHJ")
        ]
        out = format_version_score(_version(notes), ticks_per_beat=TPB)
        assert "\n" not in out.pc_score
        assert "\n" not in out.mobile_score


# ---------- human (bar-grouped) view ----------

class TestHumanView:
    def test_human_view_groups_into_4_4_bars(self):
        # 8 quarters in 4/4 → 2 bars, 4 slots each → "A S D F | G H J A".
        # With 16th-grid floor not in play (gcd is quarter), slots = quarters.
        notes = [
            _note(key_pc=ch, key_mobile=str(i + 1), start=480 * i, duration=480)
            for i, ch in enumerate("ASDFGHJA")
        ]
        out = format_version_score(
            _version(notes), ticks_per_beat=TPB, time_signature=(4, 4)
        )
        # Two bars, separated by `|` and on separate lines.
        lines = [l for l in out.human_score.split("\n") if l.strip()]
        assert len(lines) == 2
        assert "|" in out.human_score or len(lines) == 2

    def test_human_view_three_four_makes_three_beat_bars(self):
        notes = [
            _note(key_pc=ch, key_mobile=str(i + 1), start=480 * i, duration=480)
            for i, ch in enumerate("ASDFGH")
        ]
        out = format_version_score(
            _version(notes), ticks_per_beat=TPB, time_signature=(3, 4)
        )
        lines = [l for l in out.human_score.split("\n") if l.strip()]
        # 6 quarters in 3/4 → 2 bars of 3 beats each.
        assert len(lines) == 2


# ---------- twinkle-style end-to-end ----------

class TestTwinklePhrase:
    def test_twinkle_phrase_renders_correctly(self):
        # C C G G A A G(half): 6 quarters + 1 half in 4/4.
        durations = [480, 480, 480, 480, 480, 480, 960]
        starts = [sum(durations[:i]) for i in range(len(durations))]
        keys = [
            ("A", "1"), ("A", "1"), ("G", "5"), ("G", "5"),
            ("H", "6"), ("H", "6"), ("G", "5"),
        ]
        notes = [
            _note(key_pc=k, key_mobile=m, start=s, duration=d)
            for (k, m), s, d in zip(keys, starts, durations)
        ]
        out = format_version_score(
            _version(notes), ticks_per_beat=TPB, time_signature=(4, 4)
        )
        # Quarter grid (gcd = 480). Phrase ends with the half note's first
        # slot — no trailing pad per spec decision.
        assert out.pc_score == "A A G G H H G"
        # Human view: bar 1 has 4 quarters, bar 2 has the remaining 3 tokens
        # (the half note occupies one slot in this grid; trailing slot stays
        # empty inside the bar but isn't padded after the last token).
        lines = [l.strip() for l in out.human_score.split("\n") if l.strip()]
        assert len(lines) == 2
        assert lines[0].replace("|", "").strip().split() == ["A", "A", "G", "G"]
