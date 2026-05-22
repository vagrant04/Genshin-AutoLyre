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
