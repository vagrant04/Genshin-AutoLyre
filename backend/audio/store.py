"""In-memory tracking of audio transcription jobs.

Each job represents one /api/audio/transcribe request lifecycle:
download → transcribe → parse. The next plan's route updates the job
as it progresses so the frontend can poll for stage changes.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JobStage(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    PARSING = "parsing"
    DONE = "done"
    ERROR = "error"


@dataclass
class AudioJob:
    stage: JobStage = JobStage.QUEUED
    error: Optional[str] = None
    parse_token: Optional[str] = None


class AudioFileStore:
    def __init__(self) -> None:
        self._jobs: dict[str, AudioJob] = {}

    def create_job(self) -> str:
        token = f"aud_{secrets.token_hex(8)}"
        self._jobs[token] = AudioJob()
        return token

    def get(self, token: str) -> AudioJob:
        return self._jobs[token]

    def update(
        self,
        token: str,
        *,
        stage: Optional[JobStage] = None,
        error: Optional[str] = None,
        parse_token: Optional[str] = None,
    ) -> None:
        job = self._jobs[token]
        if stage is not None:
            job.stage = stage
        if error is not None:
            job.error = error
        if parse_token is not None:
            job.parse_token = parse_token
