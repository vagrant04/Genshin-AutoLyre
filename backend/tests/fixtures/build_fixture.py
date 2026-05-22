"""Generate the test fixture MIDI file.

Run:  python -m tests.fixtures.build_fixture
This produces tests/fixtures/twinkle.mid. Already committed; only re-run
if you intentionally change the fixture.
"""
from __future__ import annotations

from pathlib import Path

import mido


def build() -> mido.MidiFile:
    mid = mido.MidiFile(ticks_per_beat=480)

    # Track 0: melody — Twinkle "C C G G A A G".
    melody = mido.MidiTrack()
    melody.append(mido.MetaMessage("track_name", name="Piano Right", time=0))
    melody.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    for pitch in (60, 60, 67, 67, 69, 69, 67):
        melody.append(mido.Message("note_on", note=pitch, velocity=80, time=0))
        melody.append(mido.Message("note_off", note=pitch, velocity=0, time=480))
    mid.tracks.append(melody)

    # Track 1: column-chord accompaniment — C major, F major, G major triads.
    chords = mido.MidiTrack()
    chords.append(mido.MetaMessage("track_name", name="Piano Left", time=0))
    for root, third, fifth in [(48, 52, 55), (53, 57, 60), (55, 59, 62)]:
        chords.append(mido.Message("note_on", note=root, velocity=70, time=0))
        chords.append(mido.Message("note_on", note=third, velocity=70, time=0))
        chords.append(mido.Message("note_on", note=fifth, velocity=70, time=0))
        chords.append(mido.Message("note_off", note=root, velocity=0, time=960))
        chords.append(mido.Message("note_off", note=third, velocity=0, time=0))
        chords.append(mido.Message("note_off", note=fifth, velocity=0, time=0))
    mid.tracks.append(chords)

    # Track 2: bass line — single low notes.
    bass = mido.MidiTrack()
    bass.append(mido.MetaMessage("track_name", name="Bass", time=0))
    for pitch in (36, 41, 43):  # C2, F2, G2 — all below MIDI 48
        bass.append(mido.Message("note_on", note=pitch, velocity=80, time=0))
        bass.append(mido.Message("note_off", note=pitch, velocity=0, time=960))
    mid.tracks.append(bass)

    return mid


if __name__ == "__main__":
    out = Path(__file__).parent / "twinkle.mid"
    build().save(str(out))
    print(f"wrote {out}")
