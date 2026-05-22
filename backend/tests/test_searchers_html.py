"""Tests for individual platform searchers using httpx MockTransport.
Spec §8.1.2 (freemidi), §8.1.3 (bitmidi), §8.1.4 (musescore), §8.1.5 (bilibili)."""
from __future__ import annotations

import httpx
import pytest

from config import MusicSource
from search.freemidi import FreeMidiSearcher
from search.bitmidi import BitMidiSearcher
from search.musescore import MuseScoreSearcher
from search.bilibili import BilibiliSearcher


# ---------- FreeMIDI ----------

FREEMIDI_HTML = """
<html><body>
<div class="search-result">
  <a href="/download-12345" class="search-result-anchor">Twinkle Twinkle Little Star</a>
</div>
<div class="search-result">
  <a href="/download-67890" class="search-result-anchor">Another Tune</a>
</div>
</body></html>
"""


def _client_returning(html: str, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=html)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_freemidi_parses_search_results():
    async with _client_returning(FREEMIDI_HTML) as client:
        searcher = FreeMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.FREEMIDI
    assert "Twinkle" in results[0].title
    assert results[0].download_url == "https://freemidi.org/download2-12345"


async def test_freemidi_query_with_spaces_uses_hyphens():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=FREEMIDI_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = FreeMidiSearcher(client=client)
        await searcher.search("twinkle little star", limit=5)
    assert "twinkle-little-star" in captured["url"]


async def test_freemidi_returns_empty_on_5xx():
    async with _client_returning("server down", status=500) as client:
        searcher = FreeMidiSearcher(client=client)
        # search() catches exceptions; bad status raises in _do_search.
        results = await searcher.search("twinkle", limit=5)
    assert results == []


async def test_freemidi_respects_limit():
    async with _client_returning(FREEMIDI_HTML) as client:
        searcher = FreeMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=1)
    assert len(results) == 1


# ---------- BitMIDI ----------

BITMIDI_JSON = {
    "results": [
        {
            "name": "Twinkle Twinkle Little Star",
            "slug": "twinkle-twinkle",
            "downloadUrl": "https://bitmidi.com/uploads/twinkle-twinkle.mid",
            "fileSize": 12345,
        },
        {
            "name": "Star Wars Theme",
            "slug": "star-wars",
            "downloadUrl": "https://bitmidi.com/uploads/star-wars.mid",
            "fileSize": 54321,
        },
    ]
}


async def test_bitmidi_parses_json_api():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BITMIDI_JSON)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BitMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.BITMIDI
    assert results[0].download_url.endswith(".mid")
    # 12345 bytes ≈ 12 KB.
    assert results[0].file_size_kb in (12, 13)


async def test_bitmidi_returns_empty_on_invalid_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BitMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert results == []


# ---------- MuseScore ----------

MUSESCORE_HTML = """
<html><head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {"@type": "MusicComposition", "name": "Twinkle Variation 1", "url": "https://musescore.com/score/1"},
    {"@type": "MusicComposition", "name": "Twinkle Variation 2", "url": "https://musescore.com/score/2"}
  ]
}
</script>
</head><body></body></html>
"""


async def test_musescore_parses_jsonld():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=MUSESCORE_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = MuseScoreSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    assert results[0].source == MusicSource.MUSESCORE
    assert results[0].download_url is None
    assert "MuseScore" in (results[0].preview_keys or "")


# ---------- Bilibili ----------

BILI_API_PAGE_1 = {
    "data": {
        "result": [
            {
                "type": "video",
                "data": [
                    {
                        "bvid": "BV1abc",
                        "title": "<em>Twinkle</em> 原琴演奏",
                        "description": "MIDI 下载：https://github.com/foo/bar/twinkle.mid",
                        "duration": "0:45",
                    },
                    {
                        "bvid": "BV2def",
                        "title": "另一首曲子",
                        "description": "无下载链接",
                        "duration": "1:10",
                    },
                ],
            }
        ]
    }
}


async def test_bilibili_extracts_download_link_from_description():
    def handler(request: httpx.Request) -> httpx.Response:
        # Referer must be bilibili.com (case-insensitive header check).
        ref = request.headers.get("Referer") or request.headers.get("referer") or ""
        assert ref.startswith("https://www.bilibili.com")
        return httpx.Response(200, json=BILI_API_PAGE_1)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BilibiliSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert len(results) == 2
    has_link = next((r for r in results if r.download_url), None)
    assert has_link is not None
    assert has_link.download_url.endswith(".mid")
    no_link = next(r for r in results if not r.download_url)
    assert no_link.source_url.startswith("https://www.bilibili.com/video/")


async def test_bilibili_strips_em_tags_from_title():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=BILI_API_PAGE_1)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BilibiliSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert "<em>" not in results[0].title and "</em>" not in results[0].title
