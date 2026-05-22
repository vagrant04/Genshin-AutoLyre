"""GET /api/search route."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from search.aggregator import search_all
from search.bilibili import BilibiliSearcher
from search.bitmidi import BitMidiSearcher
from search.freemidi import FreeMidiSearcher
from search.musescore import MuseScoreSearcher

router = APIRouter(prefix="/api", tags=["search"])


def get_searchers() -> list:
    return [
        FreeMidiSearcher(),
        BitMidiSearcher(),
        MuseScoreSearcher(),
        BilibiliSearcher(),
    ]


@router.get("/search")
async def search(
    q: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    searchers: list = Depends(get_searchers),
) -> dict:
    results = await search_all(searchers, q, per_source_limit=limit)
    return {
        "query": q,
        "total": len(results),
        "results": [r.model_dump(mode="json") for r in results],
    }
