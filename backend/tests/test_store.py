"""Tests for api.store."""
from __future__ import annotations

import pytest

from config import ParsedMidi, ParsedTrack, TrackInfo, TrackRole
from api.store import ParsedFileStore


def _empty_parsed() -> ParsedMidi:
    return ParsedMidi(bpm=120, ticks_per_beat=480, tracks=[])


def _track_info(index: int, role: TrackRole) -> TrackInfo:
    return TrackInfo(
        index=index,
        name=f"Track {index}",
        note_count=10,
        pitch_range="C4~G4",
        preview_keys="A S D F",
        suggested_role=role,
        chord_type="none",
    )


def test_save_returns_token_with_prefix():
    store = ParsedFileStore()
    token = store.save(_empty_parsed(), "Title", track_infos=[])
    assert token.startswith("tmp_")


def test_get_returns_saved_record():
    store = ParsedFileStore()
    parsed = _empty_parsed()
    infos = [_track_info(0, TrackRole.MELODY)]
    token = store.save(parsed, "Title", track_infos=infos)
    record = store.get(token)
    assert record.parsed is parsed
    assert record.title == "Title"
    assert record.track_infos == infos


def test_get_unknown_token_raises_keyerror():
    store = ParsedFileStore()
    with pytest.raises(KeyError):
        store.get("tmp_nope")


def test_distinct_tokens_per_save():
    store = ParsedFileStore()
    a = store.save(_empty_parsed(), "A", track_infos=[])
    b = store.save(_empty_parsed(), "B", track_infos=[])
    assert a != b
