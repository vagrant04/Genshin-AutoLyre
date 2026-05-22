"""Tick → millisecond conversion for MIDI playback timing.

Spec: docs/superpowers/specs/2026-05-22-track-preview-design.md.
"""
from __future__ import annotations


def tick_to_ms(tick: int, *, ticks_per_beat: int, bpm: int) -> int:
    """Convert an absolute MIDI tick to milliseconds at a fixed BPM.

    We use the document-level BPM that the parser extracts. Mid-song
    tempo changes are not supported in v1.
    """
    if ticks_per_beat <= 0 or bpm <= 0:
        return 0
    return int(round(tick * 60_000 / (ticks_per_beat * bpm)))
