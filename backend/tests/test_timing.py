"""Tests for parser.timing helpers."""
from __future__ import annotations

from parser.timing import tick_to_ms


def test_tick_to_ms_basic():
    # 480 ticks at 120 BPM with 480 ticks/beat = exactly one beat = 500 ms.
    assert tick_to_ms(480, ticks_per_beat=480, bpm=120) == 500


def test_tick_to_ms_zero_tick_is_zero_ms():
    assert tick_to_ms(0, ticks_per_beat=480, bpm=120) == 0


def test_tick_to_ms_proportional():
    # Half a beat at 120 BPM = 250 ms.
    assert tick_to_ms(240, ticks_per_beat=480, bpm=120) == 250


def test_tick_to_ms_handles_different_resolution():
    # 96 ticks/beat (BitMIDI fixture's resolution), 1 beat at 120 BPM = 500ms.
    assert tick_to_ms(96, ticks_per_beat=96, bpm=120) == 500
