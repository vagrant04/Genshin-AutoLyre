"""Abstract base class for audio sources.

Mirrors the pattern in `search/base.py`: subclasses implement
`_do_search()`, the public `search()` here swallows exceptions and
returns []. `fetch_to_path()` is defined directly by subclasses
because failure modes vary per platform (paywall vs rate-limit vs
region-block) and the route layer wants to surface them distinctly.
"""
from __future__ import annotations

import abc
import logging
from pathlib import Path

from config import AudioCandidate, AudioMetadata, AudioSourceKey

_LOG = logging.getLogger(__name__)


class AbstractAudioSource(abc.ABC):
    source: AudioSourceKey

    async def search(self, query: str, limit: int = 5) -> list[AudioCandidate]:
        try:
            return await self._do_search(query, limit)
        except Exception as exc:  # noqa: BLE001 — pattern from search/base.py
            _LOG.warning("audio search failed for %s: %s", self.source, exc)
            return []

    @abc.abstractmethod
    async def _do_search(self, query: str, limit: int) -> list[AudioCandidate]:
        ...

    @abc.abstractmethod
    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata:
        ...
