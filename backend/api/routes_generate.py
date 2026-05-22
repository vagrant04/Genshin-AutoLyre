"""POST /api/generate.

Composes parser output (cached in the store) with arranger + formatter
to produce three VersionScore objects.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.errors import make_error
from api.routes_parse import get_store
from api.store import ParsedFileStore
from arranger.merger import build_three_versions
from config import (
    ChordPosition,
    LyreScore,
    MappedNote,
    ParsedNote,
    ScoreVersion,
    TrackRole,
)
from formatter.score_formatter import format_version_score
from mapper.note_mapper import map_notes
from parser.chord_grouper import group_accompaniment

router = APIRouter(prefix="/api", tags=["generate"])


class GenerateRequest(BaseModel):
    file_token: str
    title: str
    track_roles: dict[str, str]  # "0" -> "melody"


@router.post("/generate")
async def generate(
    payload: GenerateRequest,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    try:
        record = store.get(payload.file_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND")

    valid_indices = {t.index for t in record.parsed.tracks}
    parsed_roles: dict[int, TrackRole] = {}
    for raw_index, raw_role in payload.track_roles.items():
        try:
            idx = int(raw_index)
        except ValueError:
            raise make_error("INVALID_TRACK_INDEX", detail=raw_index)
        if idx not in valid_indices:
            raise make_error("INVALID_TRACK_INDEX", detail=str(idx))
        try:
            parsed_roles[idx] = TrackRole(raw_role)
        except ValueError:
            raise make_error("INVALID_TRACK_INDEX", detail=raw_role)

    if not any(role == TrackRole.MELODY for role in parsed_roles.values()):
        raise make_error("NO_MELODY_TRACK")

    melody_notes: list[MappedNote] = []
    accompaniment_notes: list[MappedNote] = []
    chord_groups: list[list[MappedNote]] = []

    for track in record.parsed.tracks:
        role = parsed_roles.get(track.index, TrackRole.IGNORED)
        if role not in (TrackRole.MELODY, TrackRole.ACCOMPANIMENT):
            continue
        # Re-tag track_role on the parsed notes before mapping.
        retagged = [
            ParsedNote(
                midi_num=n.midi_num,
                start_tick=n.start_tick,
                duration_tick=n.duration_tick,
                velocity=n.velocity,
                track_index=n.track_index,
                track_role=role,
            )
            for n in track.notes
        ]
        mapped = map_notes(retagged)
        if role == TrackRole.MELODY:
            melody_notes.extend(mapped)
        else:
            accompaniment_notes.extend(mapped)
            # Group by simultaneous start_tick (mirrors ParsedNote ordering).
            for raw_group in group_accompaniment(retagged):
                # Map indexes inside this raw group back to MappedNote objects.
                group_starts = {n.start_tick for n in raw_group}
                chord_groups.append(
                    [m for m in mapped if m.start_tick in group_starts]
                )

    versions_dict = build_three_versions(
        melody_notes=melody_notes,
        accompaniment_notes=accompaniment_notes,
        chord_groups=chord_groups,
    )

    formatted = [
        format_version_score(
            versions_dict[ScoreVersion.MELODY_ONLY],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
        format_version_score(
            versions_dict[ScoreVersion.SIMPLIFIED],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
        format_version_score(
            versions_dict[ScoreVersion.FULL],
            ticks_per_beat=record.parsed.ticks_per_beat,
        ),
    ]

    score = LyreScore(
        title=payload.title,
        bpm=record.parsed.bpm,
        ticks_per_beat=record.parsed.ticks_per_beat,
        versions=formatted,
    )
    return score.model_dump(mode="json")
