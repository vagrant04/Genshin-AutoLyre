"""Public arranger entry point.

Given the per-track MappedNote lists and the accompaniment chord
groupings the parser detected, produce three independent VersionScore
objects (melody_only / simplified / full) per spec §7.

Note: pc_score / mobile_score text is filled in later by the formatter
module (part 3 of the project). Here we only compute the note lists
and statistics.
"""
from __future__ import annotations

from config import (
    ChordPosition,
    MappedNote,
    ScoreVersion,
    TrackRole,
    VersionScore,
    VersionStats,
)
from arranger.chord_reducer import reduce_simultaneous_chord
from arranger.conflict_resolver import resolve_simultaneous_limit


_VERSION_LABELS: dict[ScoreVersion, str] = {
    ScoreVersion.MELODY_ONLY: "纯旋律版",
    ScoreVersion.SIMPLIFIED: "简化伴奏版",
    ScoreVersion.FULL: "完整伴奏版",
}


def build_three_versions(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
    chord_groups: list[list[MappedNote]],
) -> dict[ScoreVersion, VersionScore]:
    """Produce the three versions.

    `chord_groups` is the parser's grouping of `accompaniment_notes`
    into simultaneous-chord buckets (each inner list has notes whose
    start_tick differs by ≤ 30 ticks per spec §7.3 step 1). The merger
    uses these groups for the simplified version's chord reduction.
    """
    melody_sorted = sorted(melody_notes, key=lambda n: n.start_tick)

    return {
        ScoreVersion.MELODY_ONLY: _build_melody_only(melody_sorted),
        ScoreVersion.SIMPLIFIED: _build_simplified(
            melody_sorted, accompaniment_notes, chord_groups
        ),
        ScoreVersion.FULL: _build_full(melody_sorted, accompaniment_notes),
    }


def _build_melody_only(melody_notes: list[MappedNote]) -> VersionScore:
    notes = [n.model_copy() for n in melody_notes]
    return VersionScore(
        version=ScoreVersion.MELODY_ONLY,
        version_label=_VERSION_LABELS[ScoreVersion.MELODY_ONLY],
        notes=notes,
        statistics=_compute_stats(notes),
    )


def _build_simplified(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
    chord_groups: list[list[MappedNote]],
) -> VersionScore:
    # Step 1 of §7.3: chord-reduce each accompaniment group.
    reduced_accomp: list[MappedNote] = []
    grouped_ids = set()
    for group in chord_groups:
        for note in group:
            grouped_ids.add(id(note))
        reduced_accomp.extend(reduce_simultaneous_chord(group))

    # Any accompaniment note that wasn't in a group (e.g. arpeggio singles)
    # passes through untouched.
    for note in accompaniment_notes:
        if id(note) not in grouped_ids:
            reduced_accomp.append(
                note.model_copy(update={"chord_position": ChordPosition.OTHER})
            )

    # Step 2: merge melody + reduced accompaniment, sort.
    merged = sorted(
        [n.model_copy() for n in melody_notes] + reduced_accomp,
        key=lambda n: (n.start_tick, n.track_role.value),
    )

    # Step 3: enforce 4-key simultaneous limit (skips already-reduced notes).
    resolved = resolve_simultaneous_limit(merged)

    return VersionScore(
        version=ScoreVersion.SIMPLIFIED,
        version_label=_VERSION_LABELS[ScoreVersion.SIMPLIFIED],
        notes=resolved,
        statistics=_compute_stats(resolved),
    )


def _build_full(
    melody_notes: list[MappedNote],
    accompaniment_notes: list[MappedNote],
) -> VersionScore:
    merged = sorted(
        [n.model_copy() for n in melody_notes]
        + [n.model_copy() for n in accompaniment_notes],
        key=lambda n: (n.start_tick, n.track_role.value),
    )
    return VersionScore(
        version=ScoreVersion.FULL,
        version_label=_VERSION_LABELS[ScoreVersion.FULL],
        notes=merged,
        statistics=_compute_stats(merged),
    )


def _compute_stats(notes: list[MappedNote]) -> VersionStats:
    kept = [n for n in notes if not n.is_chord_reduced]
    melody = [n for n in kept if n.track_role == TrackRole.MELODY]
    accomp = [n for n in kept if n.track_role == TrackRole.ACCOMPANIMENT]
    return VersionStats(
        total_notes=len(kept),
        melody_notes=len(melody),
        accompaniment_notes=len(accomp),
        out_of_range_count=sum(1 for n in kept if n.is_out_of_range),
        semitone_count=sum(1 for n in kept if n.is_semitone_adjusted),
        chord_reduced_count=sum(1 for n in notes if n.is_chord_reduced),
        max_simultaneous_keys=_max_simultaneous(kept),
    )


def _max_simultaneous(notes: list[MappedNote]) -> int:
    if not notes:
        return 0
    distinct_starts = {n.start_tick for n in notes}
    return max(
        sum(
            1
            for n in notes
            if n.start_tick <= tick < n.start_tick + n.duration_tick
        )
        for tick in distinct_starts
    )
