"""Cross-platform search aggregator.

Spec §8.1.6:
  - asyncio.gather over all searchers, return_exceptions=True
  - Dedupe by title similarity; keep higher-score winner
  - Sort: results with download_url first; then by score descending
  - Cap total at 20.
"""
from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
from typing import Iterable, Protocol

from config import SearchResult

_SIMILARITY_THRESHOLD = 0.92
_TOTAL_CAP = 20


class _Searcher(Protocol):
    async def search(self, query: str, limit: int = 5) -> list[SearchResult]: ...


async def search_all(
    searchers: Iterable[_Searcher],
    query: str,
    *,
    per_source_limit: int = 5,
) -> list[SearchResult]:
    coros = [s.search(query, limit=per_source_limit) for s in searchers]
    settled = await asyncio.gather(*coros, return_exceptions=True)
    flat: list[SearchResult] = []
    for outcome in settled:
        if isinstance(outcome, Exception):
            continue
        flat.extend(outcome)
    return aggregate_results(flat)


def aggregate_results(results: list[SearchResult]) -> list[SearchResult]:
    deduped: list[SearchResult] = []
    for candidate in results:
        match_index = _find_similar(candidate, deduped)
        if match_index is None:
            deduped.append(candidate)
        elif candidate.score > deduped[match_index].score:
            deduped[match_index] = candidate

    deduped.sort(
        key=lambda r: (
            0 if r.download_url else 1,    # download-first
            -r.score,                       # higher score first
        )
    )
    return deduped[:_TOTAL_CAP]


def _find_similar(candidate: SearchResult, pool: list[SearchResult]) -> int | None:
    cand = _normalize(candidate.title)
    for index, existing in enumerate(pool):
        if SequenceMatcher(None, cand, _normalize(existing.title)).ratio() >= _SIMILARITY_THRESHOLD:
            return index
    return None


def _normalize(title: str) -> str:
    return "".join(ch for ch in title.lower() if ch.isalnum())
