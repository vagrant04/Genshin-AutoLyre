"""Abstract base for music searchers.

Each subclass implements `_do_search` (may raise) and `get_download_url`.
The public `search` method here wraps `_do_search` so any exception is
caught and an empty list is returned — spec §8.1.1.

`fetch_to_path` is the per-source download hook: by default it streams
the URL straight to disk via the generic downloader, but a subclass can
override it when the site needs a multi-step flow (cookies, Referer,
intermediate page visits — see FreeMidiSearcher).
"""
from __future__ import annotations

import abc
import logging
from pathlib import Path

from config import MusicSource, SearchResult
from utils.downloader import download_to_path

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

    async def fetch_to_path(self, url: str, target: Path) -> None:
        """Download the MIDI at `url` to `target`. Default is the generic
        streaming downloader. Subclasses override when the site needs
        per-platform handshake (cookies, Referer, intermediate pages)."""
        await download_to_path(url, target)
