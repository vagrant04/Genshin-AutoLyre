"""Abstract base for music searchers.

Each subclass implements `_do_search` (may raise) and `get_download_url`.
The public `search` method here wraps `_do_search` so any exception is
caught and an empty list is returned — spec §8.1.1.
"""
from __future__ import annotations

import abc
import logging

from config import MusicSource, SearchResult

_LOG = logging.getLogger(__name__)


class BaseMusicSearcher(abc.ABC):
    source: MusicSource

    async def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            return await self._do_search(query, limit)
        except Exception as exc:  # noqa: BLE001 — spec requires swallow
            _LOG.warning("search failed for %s: %s", self.source, exc)
            return []

    @abc.abstractmethod
    async def _do_search(self, query: str, limit: int) -> list[SearchResult]:
        ...

    @abc.abstractmethod
    async def get_download_url(self, result: SearchResult) -> str:
        ...
