"""Tests for audio.transcriber.

These tests exercise the real Basic Pitch transcription on the
fixture MP3 — the first run is slow because TensorFlow lazy-loads
the model (~30 s on CPU). Subsequent runs in the same process are
fast (~3 s for a 10-s clip).
"""
from __future__ import annotations

from pathlib import Path

import pytest
import mido

from audio.exceptions import TranscriptionError
from audio.transcriber import transcribe

FIXTURE = Path(__file__).parent / "fixtures" / "ten_seconds_piano.mp3"


pytestmark = pytest.mark.slow


async def test_transcribes_to_midi(tmp_path: Path):
    out = tmp_path / "out.mid"
    result = await transcribe(FIXTURE, out)
    assert result == out
    assert out.is_file()
    assert out.stat().st_size > 0


async def test_output_midi_is_parseable(tmp_path: Path):
    out = tmp_path / "out.mid"
    await transcribe(FIXTURE, out)
    midi = mido.MidiFile(str(out))
    note_count = sum(
        1
        for track in midi.tracks
        for msg in track
        if msg.type == "note_on" and msg.velocity > 0
    )
    assert note_count > 0


async def test_transcribe_missing_file_raises(tmp_path: Path):
    bogus = tmp_path / "nope.mp3"
    out = tmp_path / "out.mid"
    with pytest.raises(TranscriptionError, match="audio file not found"):
        await transcribe(bogus, out)
