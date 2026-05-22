"""Tests for arranger.merger.build_three_versions. Spec §7, §11.4."""
from __future__ import annotations

from config import ChordPosition, MappedNote, ScoreVersion, TrackRole
from arranger.merger import build_three_versions


def _n(
    midi: int,
    role: TrackRole,
    *,
    start: int = 0,
    duration: int = 480,
) -> MappedNote:
    return MappedNote(
        original_midi=midi,
        mapped_midi=midi,
        key_pc="A",
        key_mobile="1",
        start_tick=start,
        duration_tick=duration,
        track_role=role,
    )


def _kept(notes):
    return [n for n in notes if not n.is_chord_reduced]


class TestMelodyOnlyVersion:
    def test_excludes_all_accompaniment(self):
        melody = [_n(60, TrackRole.MELODY, start=0), _n(62, TrackRole.MELODY, start=480)]
        accomp = [_n(48, TrackRole.ACCOMPANIMENT, start=0)]
        result = build_three_versions(melody, accomp, chord_groups=[[accomp[0]]])
        v1 = result[ScoreVersion.MELODY_ONLY]
        kept = _kept(v1.notes)
        assert all(n.track_role == TrackRole.MELODY for n in kept)
        assert len(kept) == 2


class TestSimplifiedVersion:
    def test_max_simultaneous_within_limit(self):
        # 3 melody + 3 accompaniment all at tick 0 → must be ≤ 4 after merge.
        melody = [
            _n(60, TrackRole.MELODY, start=0),
            _n(64, TrackRole.MELODY, start=0),
            _n(67, TrackRole.MELODY, start=0),
        ]
        accomp = [
            _n(48, TrackRole.ACCOMPANIMENT, start=0),
            _n(52, TrackRole.ACCOMPANIMENT, start=0),
            _n(55, TrackRole.ACCOMPANIMENT, start=0),
        ]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v2 = result[ScoreVersion.SIMPLIFIED]
        assert v2.statistics.max_simultaneous_keys <= 4

    def test_melody_count_preserved_under_pressure(self):
        melody = [_n(60 + i * 2, TrackRole.MELODY, start=0) for i in range(3)]
        accomp = [_n(48 + i * 2, TrackRole.ACCOMPANIMENT, start=0) for i in range(3)]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v2 = result[ScoreVersion.SIMPLIFIED]
        assert v2.statistics.melody_notes == 3


class TestFullVersion:
    def test_all_notes_kept(self):
        melody = [_n(60, TrackRole.MELODY, start=0), _n(62, TrackRole.MELODY, start=480)]
        accomp = [
            _n(48, TrackRole.ACCOMPANIMENT, start=0),
            _n(52, TrackRole.ACCOMPANIMENT, start=0),
            _n(55, TrackRole.ACCOMPANIMENT, start=0),
            _n(48, TrackRole.ACCOMPANIMENT, start=480),
        ]
        result = build_three_versions(melody, accomp, chord_groups=[accomp[:3], [accomp[3]]])
        v3 = result[ScoreVersion.FULL]
        kept = _kept(v3.notes)
        assert len(kept) == len(melody) + len(accomp)
        assert v3.statistics.total_notes == len(kept)
        # Stats invariant from spec §11.4.
        assert (
            v3.statistics.total_notes
            == v3.statistics.melody_notes + v3.statistics.accompaniment_notes
        )

    def test_full_allows_more_than_four_simultaneous(self):
        # 3 melody + 3 accompaniment all at tick 0 → full version keeps 6.
        melody = [_n(60 + i, TrackRole.MELODY, start=0) for i in (0, 2, 4)]
        accomp = [_n(48 + i, TrackRole.ACCOMPANIMENT, start=0) for i in (0, 4, 7)]
        result = build_three_versions(melody, accomp, chord_groups=[accomp])
        v3 = result[ScoreVersion.FULL]
        assert v3.statistics.max_simultaneous_keys == 6


class TestVersionLabels:
    def test_three_versions_returned(self):
        result = build_three_versions([], [], chord_groups=[])
        assert set(result.keys()) == {
            ScoreVersion.MELODY_ONLY,
            ScoreVersion.SIMPLIFIED,
            ScoreVersion.FULL,
        }

    def test_chinese_labels(self):
        result = build_three_versions([], [], chord_groups=[])
        assert result[ScoreVersion.MELODY_ONLY].version_label == "纯旋律版"
        assert result[ScoreVersion.SIMPLIFIED].version_label == "简化伴奏版"
        assert result[ScoreVersion.FULL].version_label == "完整伴奏版"
