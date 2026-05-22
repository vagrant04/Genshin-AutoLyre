"""Enforce the 4-key simultaneous limit for the simplified version.

Spec §7.3 step 3 / §8.4.3:
  - At every start_tick of every note, count how many notes are sounding.
  - If >4, drop accompaniment notes (NEVER melody) in priority order:
    third → fifth → root → other.
  - If melody alone is already >4, leave it: melody is never cut.

This module mutates `is_chord_reduced` only. It does not delete entries
from the list.
"""
from __future__ import annotations

from config import ChordPosition, MappedNote, TrackRole
from mapper.constants import SIMPLIFIED_MAX_SIMULTANEOUS

# Lower priority value = removed first.
_REMOVAL_PRIORITY: dict[ChordPosition, int] = {
    ChordPosition.OTHER: 0,
    ChordPosition.THIRD: 1,
    ChordPosition.FIFTH: 2,
    ChordPosition.ROOT: 3,
}


def resolve_simultaneous_limit(notes: list[MappedNote]) -> list[MappedNote]:
    """Mark accompaniment notes as `is_chord_reduced` until no instant
    has more than 4 simultaneous *kept* notes (or only melody remains)."""
    # Work on copies so we don't mutate caller-owned objects.
    working: list[MappedNote] = [n.model_copy() for n in notes]

    # Check at every distinct start_tick: that's where note counts change.
    distinct_starts = sorted({n.start_tick for n in working})

    for tick in distinct_starts:
        sounding_indices = [
            i for i, n in enumerate(working)
            if not n.is_chord_reduced
            and n.start_tick <= tick < n.start_tick + n.duration_tick
        ]
        while len(sounding_indices) > SIMPLIFIED_MAX_SIMULTANEOUS:
            accompaniment_indices = [
                i for i in sounding_indices
                if working[i].track_role == TrackRole.ACCOMPANIMENT
            ]
            if not accompaniment_indices:
                # Pure-melody overload — spec says leave it.
                break
            # Pick the accompaniment note with the lowest removal priority.
            victim = min(
                accompaniment_indices,
                key=lambda i: (
                    _REMOVAL_PRIORITY[working[i].chord_position],
                    working[i].mapped_midi,
                ),
            )
            working[victim] = working[victim].model_copy(
                update={"is_chord_reduced": True}
            )
            sounding_indices = [
                i for i, n in enumerate(working)
                if not n.is_chord_reduced
                and n.start_tick <= tick < n.start_tick + n.duration_tick
            ]
    return working
