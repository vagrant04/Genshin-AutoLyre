"""Score text formatter.

Pure transform: VersionScore + ticks_per_beat → VersionScore with
pc_score and mobile_score populated. Spec §8.5.

Rules:
  - Notes whose start_tick differs by ≤ 30 ticks group into a chord token.
    PC chord: "(ADG)" — uppercase letters concatenated inside parens.
    Mobile chord: "(135)" — sign+digit tokens concatenated.
  - Out-of-range notes wrap in square brackets: "[Q]" / "[+1]". For chord
    members that are out of range, each member is wrapped individually
    inside the chord parens, e.g. "(A[Q]D)".
  - A gap > 1 beat (i.e. > ticks_per_beat) between successive groups
    inserts " - " between them.
  - Lines wrap to keep at most 16 tokens per line.
  - Notes with is_chord_reduced=True are excluded from output entirely.
"""
from __future__ import annotations

from config import MappedNote, VersionScore

CHORD_TOLERANCE_TICKS = 30
LINE_TOKEN_LIMIT = 16


def format_version_score(
    version: VersionScore,
    *,
    ticks_per_beat: int,
) -> VersionScore:
    """Return a new VersionScore with pc_score / mobile_score filled in."""
    visible = [n for n in version.notes if not n.is_chord_reduced]
    if not visible:
        return version.model_copy(update={"pc_score": "", "mobile_score": ""})

    visible.sort(key=lambda n: n.start_tick)
    groups = _group_simultaneous(visible)

    pc_tokens = _build_token_stream(groups, ticks_per_beat, mode="pc")
    mobile_tokens = _build_token_stream(groups, ticks_per_beat, mode="mobile")
    return version.model_copy(
        update={
            "pc_score": _wrap_lines(pc_tokens),
            "mobile_score": _wrap_lines(mobile_tokens),
        }
    )


def _group_simultaneous(notes: list[MappedNote]) -> list[list[MappedNote]]:
    groups: list[list[MappedNote]] = [[notes[0]]]
    for note in notes[1:]:
        if abs(note.start_tick - groups[-1][0].start_tick) <= CHORD_TOLERANCE_TICKS:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _build_token_stream(
    groups: list[list[MappedNote]],
    ticks_per_beat: int,
    *,
    mode: str,
) -> list[str]:
    tokens: list[str] = []
    prev_end_tick: int | None = None
    for group in groups:
        group_start = min(n.start_tick for n in group)
        if prev_end_tick is not None:
            gap = group_start - prev_end_tick
            if gap > ticks_per_beat:
                tokens.append("-")
        tokens.append(_render_group(group, mode=mode))
        prev_end_tick = max(n.start_tick + n.duration_tick for n in group)
    return tokens


def _render_group(group: list[MappedNote], *, mode: str) -> str:
    if len(group) == 1:
        return _render_single(group[0], mode=mode)
    inner = "".join(_render_single(n, mode=mode) for n in group)
    return f"({inner})"


def _render_single(note: MappedNote, *, mode: str) -> str:
    base = note.key_pc if mode == "pc" else note.key_mobile
    return f"[{base}]" if note.is_out_of_range else base


def _wrap_lines(tokens: list[str]) -> str:
    lines: list[str] = []
    current: list[str] = []
    note_count = 0  # count of non-rest tokens
    for token in tokens:
        current.append(token)
        if token != "-":
            note_count += 1
        if note_count >= LINE_TOKEN_LIMIT:
            lines.append(" ".join(current))
            current = []
            note_count = 0
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)
