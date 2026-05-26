"""Column-chord reduction for the simplified version.

Given a set of simultaneous accompaniment notes, label each by chord
position (root / fifth / third / other) and mark the ones that should
be dropped. Per spec §8.4.1: keep the root, the closest fifth above
root, and the closest third above root, up to 3 notes total.

This module ONLY labels — it never deletes from the list. Downstream
consumers filter on `is_chord_reduced`.
"""
from __future__ import annotations

from config import ChordPosition, MappedNote


def reduce_simultaneous_chord(group: list[MappedNote]) -> list[MappedNote]:
    """Label and reduce a group of simultaneous accompaniment notes.

    Returned list is the same length as input; each note has
    `chord_position` set and `is_chord_reduced` set to True for notes
    that should not appear in the simplified output.
    """
    if not group:
        return []
    if len(group) == 1:
        sole = group[0].model_copy(update={"chord_position": ChordPosition.ROOT})
        return [sole]

    # Sort ascending by mapped_midi so the lowest note is the root.
    by_pitch = sorted(group, key=lambda n: n.mapped_midi)
    root = by_pitch[0]

    # Closest fifth above root: prefer +7 semitones, fall back to nearest
    # remaining note that is at least a perfect fourth above root.
    rest = list(by_pitch[1:])
    fifth = _pick_closest_to(rest, target=root.mapped_midi + 7)
    if fifth is not None:
        rest.remove(fifth)

    # Closest third above root: prefer +4 (major) then +3 (minor).
    third = _pick_closest_to(rest, target=root.mapped_midi + 4)
    if third is None:
        third = _pick_closest_to(rest, target=root.mapped_midi + 3)
    if third is not None:
        rest.remove(third)

    output: list[MappedNote] = []
    for note in group:
        if note is root:
            output.append(note.model_copy(update={"chord_position": ChordPosition.ROOT}))
        elif fifth is not None and note is fifth:
            output.append(note.model_copy(update={"chord_position": ChordPosition.FIFTH}))
        elif third is not None and note is third:
            output.append(note.model_copy(update={"chord_position": ChordPosition.THIRD}))
        else:
            output.append(note.model_copy(update={
                "chord_position": ChordPosition.OTHER,
                "is_chord_reduced": True,
            }))
    return output


def _pick_closest_to(candidates: list[MappedNote], target: int) -> MappedNote | None:
    if not candidates:
        return None
    return min(candidates, key=lambda n: abs(n.mapped_midi - target))
