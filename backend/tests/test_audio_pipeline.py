"""Tests for audio.pipeline.run_transcribe_pipeline.

The orchestrator is exercised offline via dependency injection:
- A fake AudioSource writes a known byte string to the target path.
- A fake transcriber writes a small MIDI to the target path (using mido).
- A real ParsedFileStore captures the parse output.

We verify the full sequence: cache miss → download → transcribe →
parse → store update; cache hit short-circuits.
"""
from __future__ import annotations

from pathlib import Path

import mido
import pytest

from audio.exceptions import SourceUnavailable, TranscriptionError
from audio.pipeline import run_transcribe_pipeline, TranscribeRequest
from audio.store import AudioFileStore, JobStage
from api.store import ParsedFileStore
from config import AudioMetadata, AudioSourceKey


def _build_tiny_midi(path: Path) -> None:
    """Write a 1-track, 1-note MIDI to `path`."""
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Piano", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=80, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    mid.save(str(path))


class _StubSource:
    source = AudioSourceKey.YOUTUBE

    def __init__(self, payload: bytes = b"FAKE_AUDIO"):
        self._payload = payload
        self.fetch_calls = 0

    async def search(self, query, limit=5): return []

    async def fetch_to_path(self, url: str, target: Path):
        self.fetch_calls += 1
        target.write_bytes(self._payload)
        return AudioMetadata(
            source=self.source,
            canonical_url=url,
            title="stub song",
            duration_seconds=120,
            file_path=str(target),
            file_size_bytes=len(self._payload),
        )


async def _stub_transcribe(audio_path: Path, midi_out_path: Path, **kwargs):
    """Drop a tiny MIDI into the requested output path."""
    _build_tiny_midi(midi_out_path)
    return midi_out_path


async def test_pipeline_completes_full_sequence(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://www.youtube.com/watch?v=abc",
        title="Twinkle",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    await run_transcribe_pipeline(
        job_token=job_token,
        request=req,
        source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store,
        audio_store=audio_store,
        cache_root=tmp_path,
    )

    job = audio_store.get(job_token)
    assert job.stage == JobStage.DONE
    assert job.parse_token is not None
    assert job.parse_token.startswith("tmp_")
    record = parse_store.get(job.parse_token)
    assert record.title == "Twinkle"


async def test_pipeline_uses_cached_audio_on_repeat(tmp_path: Path):
    """Second invocation with the same URL skips the download."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://example.com/x",
        title="x",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    t1 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t1, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    t2 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t2, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert src.fetch_calls == 1


async def test_pipeline_uses_cached_midi_on_repeat(tmp_path: Path):
    """Same URL + same params → MIDI cache hit, transcriber not called twice."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    src = _StubSource()
    req = TranscribeRequest(
        canonical_url="https://example.com/y",
        title="y",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )

    transcribe_calls = 0

    async def _counting(audio_path, midi_out_path, **kwargs):
        nonlocal transcribe_calls
        transcribe_calls += 1
        _build_tiny_midi(midi_out_path)
        return midi_out_path

    t1 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t1, request=req, source=src,
        transcribe_fn=_counting,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    t2 = audio_store.create_job()
    await run_transcribe_pipeline(
        job_token=t2, request=req, source=src,
        transcribe_fn=_counting,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert transcribe_calls == 1


async def test_pipeline_marks_error_on_source_failure(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    class _Failing:
        source = AudioSourceKey.QQMUSIC
        async def search(self, q, limit=5): return []
        async def fetch_to_path(self, url, target):
            raise SourceUnavailable("paywalled")

    req = TranscribeRequest(
        canonical_url="https://y.qq.com/n/ryqq/songDetail/abc",
        title="paywall",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=_Failing(),
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    job = audio_store.get(job_token)
    assert job.stage == JobStage.ERROR
    assert "paywalled" in (job.error or "")


async def test_pipeline_marks_error_on_transcription_failure(tmp_path: Path):
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()
    src = _StubSource()

    async def _bad_transcribe(audio_path, midi_out_path, **kwargs):
        raise TranscriptionError("model crashed")

    req = TranscribeRequest(
        canonical_url="https://example.com/crash",
        title="x",
        onset_threshold=0.5,
        min_note_length_ms=60,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=src,
        transcribe_fn=_bad_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    job = audio_store.get(job_token)
    assert job.stage == JobStage.ERROR
    assert "model crashed" in (job.error or "")


async def test_pipeline_uses_local_upload_path(tmp_path: Path):
    """When `local_audio_path` is set, source.fetch_to_path is never called."""
    audio_store = AudioFileStore()
    parse_store = ParsedFileStore()
    job_token = audio_store.create_job()

    local_audio = tmp_path / "uploaded.mp3"
    local_audio.write_bytes(b"UPLOADED_AUDIO")

    src = _StubSource()
    req = TranscribeRequest(
        canonical_url=None,
        title="uploaded.mp3",
        onset_threshold=0.5,
        min_note_length_ms=60,
        local_audio_path=local_audio,
    )
    await run_transcribe_pipeline(
        job_token=job_token, request=req, source=src,
        transcribe_fn=_stub_transcribe,
        parse_store=parse_store, audio_store=audio_store, cache_root=tmp_path,
    )
    assert src.fetch_calls == 0
    assert audio_store.get(job_token).stage == JobStage.DONE
