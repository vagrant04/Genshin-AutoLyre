"""GET /api/preview-track.

Returns a flat note list (with absolute millisecond timing) for a single
track of a previously-parsed MIDI, in either raw or lyre-mapped form.
The frontend feeds these notes into a Tone.js Sampler so the user can
audition each track before deciding which is the melody.

Spec: docs/superpowers/specs/2026-05-22-track-preview-design.md.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from api.errors import make_error
from api.routes_parse import get_store
from api.store import ParsedFileStore
from mapper.note_mapper import map_note
from parser.timing import tick_to_ms

router = APIRouter(prefix="/api", tags=["preview"])


@router.get("/preview-track")
async def preview_track(
    file_token: Annotated[str, Query()],
    track_index: Annotated[int, Query(ge=0)],
    mapped: Annotated[bool, Query()],
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    try:
        record = store.get(file_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND")

    track = next(
        (t for t in record.parsed.tracks if t.index == track_index),
        None,
    )
    if track is None:
        raise make_error("INVALID_TRACK_INDEX", detail=str(track_index))

    bpm = record.parsed.bpm
    tpb = record.parsed.ticks_per_beat

    notes_out: list[dict] = []
    max_end_ms = 0
    for parsed_note in track.notes:
        if mapped:
            mapped_note = map_note(parsed_note)
            midi = mapped_note.mapped_midi
        else:
            midi = parsed_note.midi_num
        start_ms = tick_to_ms(parsed_note.start_tick, ticks_per_beat=tpb, bpm=bpm)
        duration_ms = tick_to_ms(
            parsed_note.duration_tick, ticks_per_beat=tpb, bpm=bpm
        )
        # Guarantee a non-zero duration so the synth still triggers for
        # extremely short notes after rounding.
        if duration_ms <= 0:
            duration_ms = 1
        notes_out.append({
            "midi": midi,
            "start_ms": start_ms,
            "duration_ms": duration_ms,
            "velocity": parsed_note.velocity,
        })
        max_end_ms = max(max_end_ms, start_ms + duration_ms)

    return {
        "track_index": track.index,
        "track_name": track.name,
        "mapped": mapped,
        "bpm": bpm,
        "ticks_per_beat": tpb,
        "duration_ms": max_end_ms,
        "notes": notes_out,
    }
