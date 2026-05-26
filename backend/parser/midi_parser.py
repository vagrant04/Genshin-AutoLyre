"""MIDI file parser.

Reads a local MIDI path with mido and produces a ParsedMidi. The route
layer is responsible for downloading first; this module is filesystem-only.

Per spec §8.2.1 we filter out:
  - note_on with velocity 0 (these are alternative note-off encodings)
  - notes shorter than 30 ticks (likely artifacts)
"""
from __future__ import annotations

from pathlib import Path

import mido

from config import ParsedMidi, ParsedNote, ParsedTrack, TrackRole

MIN_DURATION_TICK = 30


class ParseError(Exception):
    """Raised when a MIDI file cannot be opened or parsed."""


def parse_midi_file(path: Path) -> ParsedMidi:
    if not path.is_file():
        raise ParseError(f"MIDI file not found: {path}")
    try:
        midi = mido.MidiFile(str(path))
    except (OSError, EOFError, ValueError) as exc:
        raise ParseError(f"Failed to parse MIDI: {exc}") from exc

    bpm = _extract_bpm(midi)
    time_signature = _extract_time_signature(midi)
    tracks: list[ParsedTrack] = []
    for index, track in enumerate(midi.tracks):
        name = _extract_track_name(track) or f"轨道 {index}"
        notes = _extract_notes(track, track_index=index)
        tracks.append(ParsedTrack(index=index, name=name, notes=notes))

    return ParsedMidi(
        bpm=bpm,
        ticks_per_beat=midi.ticks_per_beat,
        tracks=tracks,
        time_signature=time_signature,
    )


def _extract_bpm(midi: mido.MidiFile) -> int:
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return int(round(mido.tempo2bpm(msg.tempo)))
    return 120  # spec default


def _extract_time_signature(midi: mido.MidiFile) -> tuple[int, int]:
    """Return the first time_signature meta event as (num, den), or (4, 4)."""
    for track in midi.tracks:
        for msg in track:
            if msg.type == "time_signature":
                return (int(msg.numerator), int(msg.denominator))
    return (4, 4)


def _extract_track_name(track: mido.MidiTrack) -> str | None:
    for msg in track:
        if msg.type == "track_name":
            return msg.name
    return None


def _extract_notes(track: mido.MidiTrack, *, track_index: int) -> list[ParsedNote]:
    """Walk a track, pair note_on/note_off into ParsedNote objects."""
    notes: list[ParsedNote] = []
    open_notes: dict[int, tuple[int, int]] = {}  # pitch -> (start_tick, velocity)
    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            open_notes[msg.note] = (abs_tick, msg.velocity)
        elif (
            msg.type == "note_off"
            or (msg.type == "note_on" and msg.velocity == 0)
        ):
            opened = open_notes.pop(msg.note, None)
            if opened is None:
                continue
            start_tick, velocity = opened
            duration = abs_tick - start_tick
            if duration < MIN_DURATION_TICK:
                continue
            notes.append(
                ParsedNote(
                    midi_num=msg.note,
                    start_tick=start_tick,
                    duration_tick=duration,
                    velocity=velocity,
                    track_index=track_index,
                    track_role=TrackRole.IGNORED,  # placeholder until classified
                )
            )
    return notes
