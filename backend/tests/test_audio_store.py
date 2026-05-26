"""Tests for AudioFileStore."""
from __future__ import annotations

import pytest

from audio.store import AudioFileStore, JobStage


def test_create_returns_token_with_prefix():
    store = AudioFileStore()
    token = store.create_job()
    assert token.startswith("aud_")


def test_get_returns_initial_state():
    store = AudioFileStore()
    token = store.create_job()
    job = store.get(token)
    assert job.stage == JobStage.QUEUED
    assert job.error is None
    assert job.parse_token is None


def test_update_stage():
    store = AudioFileStore()
    token = store.create_job()
    store.update(token, stage=JobStage.DOWNLOADING)
    assert store.get(token).stage == JobStage.DOWNLOADING


def test_complete_with_parse_token():
    store = AudioFileStore()
    token = store.create_job()
    store.update(token, stage=JobStage.DONE, parse_token="tmp_xyz")
    job = store.get(token)
    assert job.stage == JobStage.DONE
    assert job.parse_token == "tmp_xyz"


def test_get_unknown_raises_keyerror():
    store = AudioFileStore()
    with pytest.raises(KeyError):
        store.get("aud_nope")


def test_update_unknown_raises_keyerror():
    store = AudioFileStore()
    with pytest.raises(KeyError):
        store.update("aud_nope", stage=JobStage.DONE)
