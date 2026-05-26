"""Score text formatter — rhythm-aware grid encoding.

Each note (or simultaneous-note chord) occupies one slot. The slot
duration is auto-detected per song (GCD of all note start_tick deltas
and durations), with a 32nd-note floor so a single grace-note tick
can't blow up the output. Empty slots are rendered as a single space
so the visual gap between tokens encodes rhythm directly.

Three outputs per VersionScore:
  - pc_score: one continuous line, e.g. "A   A   G G   H".
  - mobile_score: same grid with mobile keys ("1   1   5 5   6").
  - human_score: same grid grouped into bars, one bar per line, with
    "| " between bars on the same line is unused — bars wrap to new lines
    so the reader can scan one bar at a time. Bar length comes from
    the file's time signature (default 4/4).

Rules applied to each slot:
  - Notes whose start_tick differs by ≤ 30 ticks group into a chord token.
  - PC chord: "(ADG)" — uppercase letters concatenated inside parens.
  - Mobile chord: "(135)" — sign+digit tokens concatenated.
  - Out-of-range notes wrap in square brackets: "[Q]" / "[+1]".
  - Notes with is_chord_reduced=True are excluded.
"""
from __future__ import annotations

from math import gcd
from typing import Iterable

from config import MappedNote, VersionScore

CHORD_TOLERANCE_TICKS = 30
SUBDIVISION_FLOOR_DIVISOR = 8  # 32nd note when ticks_per_beat is the standard


def format_version_score(
    version: VersionScore,
    *,
    ticks_per_beat: int,
    time_signature: tuple[int, int] = (4, 4),
) -> VersionScore:
    """Return a new VersionScore with pc_score / mobile_score / human_score
    populated."""
    visible = [n for n in version.notes if not n.is_chord_reduced]
    if not visible:
        return version.model_copy(update={
            "pc_score": "",
            "mobile_score": "",
            "human_score": "",
        })

    visible.sort(key=lambda n: n.start_tick)
    groups = _group_simultaneous(visible)
    slot_ticks = _detect_slot_ticks(groups, ticks_per_beat)

    # Place each group on its slot index. Multiple groups landing on the
    # same slot (very rare — only if the chord-tolerance grouping missed
    # them) are merged so the grid stays consistent.
    grid: dict[int, list[MappedNote]] = {}
    base_tick = groups[0][0].start_tick  # treat the first note as t=0
    for group in groups:
        slot = (group[0].start_tick - base_tick) // slot_ticks
        grid.setdefault(slot, []).extend(group)
    last_slot = max(grid.keys())

    pc_tokens = _render_grid(grid, last_slot, mode="pc")
    mobile_tokens = _render_grid(grid, last_slot, mode="mobile")

    pc_score = " ".join(pc_tokens)
    mobile_score = " ".join(mobile_tokens)
    human_score = _render_human(
        grid,
        last_slot,
        slot_ticks=slot_ticks,
        ticks_per_beat=ticks_per_beat,
        time_signature=time_signature,
    )

    return version.model_copy(update={
        "pc_score": pc_score,
        "mobile_score": mobile_score,
        "human_score": human_score,
    })


# ---------- grouping ----------

def _group_simultaneous(notes: list[MappedNote]) -> list[list[MappedNote]]:
    groups: list[list[MappedNote]] = [[notes[0]]]
    for note in notes[1:]:
        if abs(note.start_tick - groups[-1][0].start_tick) <= CHORD_TOLERANCE_TICKS:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


# ---------- subdivision detection ----------

def _detect_slot_ticks(
    groups: list[list[MappedNote]],
    ticks_per_beat: int,
) -> int:
    """Auto-detect the slot duration as the GCD of all start-tick deltas
    and note durations, clamped to a 32nd-note floor."""
    floor = max(1, ticks_per_beat // SUBDIVISION_FLOOR_DIVISOR)

    deltas: list[int] = []
    starts = sorted({g[0].start_tick for g in groups})
    for i in range(1, len(starts)):
        delta = starts[i] - starts[i - 1]
        if delta > 0:
            deltas.append(delta)
    for group in groups:
        for note in group:
            if note.duration_tick > 0:
                deltas.append(note.duration_tick)

    if not deltas:
        return ticks_per_beat  # single note → arbitrary

    detected = deltas[0]
    for d in deltas[1:]:
        detected = gcd(detected, d)

    return max(detected, floor)


# ---------- token rendering ----------

def _render_grid(
    grid: dict[int, list[MappedNote]],
    last_slot: int,
    *,
    mode: str,
) -> list[str]:
    """Build a list of slot tokens — note token at filled slots, empty
    string at empty slots. The caller joins with single spaces."""
    tokens: list[str] = []
    for slot in range(last_slot + 1):
        notes_here = grid.get(slot)
        if notes_here is None:
            tokens.append("")
        else:
            tokens.append(_render_group(notes_here, mode=mode))
    return tokens


def _render_group(group: list[MappedNote], *, mode: str) -> str:
    if len(group) == 1:
        return _render_single(group[0], mode=mode)
    inner = "".join(_render_single(n, mode=mode) for n in group)
    return f"({inner})"


def _render_single(note: MappedNote, *, mode: str) -> str:
    base = note.key_pc if mode == "pc" else note.key_mobile
    return f"[{base}]" if note.is_out_of_range else base


# ---------- human (bar-grouped) view ----------

def _render_human(
    grid: dict[int, list[MappedNote]],
    last_slot: int,
    *,
    slot_ticks: int,
    ticks_per_beat: int,
    time_signature: tuple[int, int],
) -> str:
    """Group slots into bars. Each bar gets its own line, prefixed with
    `| ` and suffixed with ` |`. Trailing empty slots within the final
    bar are kept (so the bar's visual width is consistent), but bars
    after the last note are dropped (no trailing pad — spec decision)."""
    numerator, denominator = time_signature
    # Bar length in ticks: numerator * (whole-note ticks / denominator).
    whole_note_ticks = ticks_per_beat * 4
    bar_ticks = numerator * (whole_note_ticks // max(denominator, 1))
    slots_per_bar = max(1, bar_ticks // slot_ticks)

    pc_tokens = _render_grid(grid, last_slot, mode="pc")

    bars: list[str] = []
    bar_start = 0
    while bar_start <= last_slot:
        bar_end = min(bar_start + slots_per_bar - 1, last_slot)
        bar_slots = pc_tokens[bar_start : bar_end + 1]
        # Skip a bar that is entirely empty (only happens at the very
        # end if a previous bar's last note happened to fall on the bar
        # boundary). We don't want trailing blank bars.
        if any(tok != "" for tok in bar_slots):
            bars.append("| " + " ".join(bar_slots) + " |")
        bar_start += slots_per_bar
    return "\n".join(bars)
