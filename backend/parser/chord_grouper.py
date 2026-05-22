"""Group accompaniment notes into simultaneous chord groups.

Spec §7.3 step 1: notes whose start_tick differs by at most 30 ticks
belong to the same chord group. The arranger consumes these groups
when reducing column chords for the simplified version.
"""
from __future__ import annotations

from config import ParsedNote

GROUP_TOLERANCE_TICKS = 30


def group_accompaniment(notes: list[ParsedNote]) -> list[list[ParsedNote]]:
    if not notes:
        return []
    sorted_notes = sorted(notes, key=lambda n: n.start_tick)
    groups: list[list[ParsedNote]] = [[sorted_notes[0]]]
    for note in sorted_notes[1:]:
        anchor = groups[-1][0].start_tick
        if abs(note.start_tick - anchor) <= GROUP_TOLERANCE_TICKS:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups
