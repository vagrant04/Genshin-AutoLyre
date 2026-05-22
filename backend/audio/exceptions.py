"""Audio package exception hierarchy.

These are normal Python exceptions raised by the audio package; the
FastAPI route layer (next plan) maps them to ApiError codes from the
existing error catalog.
"""
from __future__ import annotations


class AudioError(Exception):
    """Base for all audio-pipeline errors."""


class SourceUnavailable(AudioError):
    """The source platform's API/library failed (paywall, region block,
    rate limit, broken upstream). User-facing message will be generic;
    `detail` carries the technical reason."""


class AudioTooLargeError(AudioError):
    """Audio file exceeded the 50 MB size cap."""


class AudioTooLongError(AudioError):
    """Audio duration exceeded the 10-minute cap."""


class TranscriptionError(AudioError):
    """Basic Pitch failed to transcribe (corrupt audio, OOM, etc.)."""


class InvalidAudioUrlError(AudioError):
    """URL host did not match any known source platform."""
