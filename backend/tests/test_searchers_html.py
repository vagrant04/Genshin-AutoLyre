"""Tests for individual platform searchers using httpx MockTransport.

Note: These mocks reflect the actual responses observed against the live
sites in May 2026. The original spec descriptions of FreeMIDI/BitMIDI URL
patterns turned out to be incorrect; the implementations here use the
real working endpoints.
"""
from __future__ import annotations

import httpx
import pytest

from config import MusicSource
from search.freemidi import FreeMidiSearcher
from search.bitmidi import BitMidiSearcher
from search.musescore import MuseScoreSearcher
from search.bilibili import BilibiliSearcher


# ---------- FreeMIDI ----------

# Real FreeMIDI search results contain anchors with /download3-{id}-{slug}.
FREEMIDI_HTML = """
<html><body>
<div>
  <a href="/download3-12345-twinkle-twinkle-little-star">Twinkle Twinkle Little Star</a>
  <a href="/download3-67890-another-tune">Another Tune</a>
  <a href="/help">Help</a>
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
    # Download URL uses /getter-{id} pattern (the real download endpoint).
    assert results[0].download_url == "https://freemidi.org/getter-12345"


async def test_freemidi_uses_query_param():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=FREEMIDI_HTML)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = FreeMidiSearcher(client=client)
        await searcher.search("twinkle little star", limit=5)
    # Real site uses ?q=... param, not slug-in-path.
    assert "q=twinkle" in captured["url"]


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


async def test_freemidi_dedupes_repeat_links():
    """Real freemidi pages render each result twice (the linked title + the
    download button). Our parser must dedupe by ID."""
    html = """<html><body>
        <a href="/download3-12345-x">Title</a>
        <a href="/download3-12345-x"><img src="dl.png"/></a>
    </body></html>"""
    async with _client_returning(html) as client:
        searcher = FreeMidiSearcher(client=client)
        results = await searcher.search("x", limit=5)
    assert len(results) == 1


# ---------- BitMIDI ----------

# Mirrors the actual /api/midi/all response envelope.
BITMIDI_JSON = {
    "result": {
        "results": [
            {
                "id": 24946,
                "name": "Coldplay - Viva La Vida.mid",
                "slug": "coldplay-viva-la-vida-mid",
                "url": "/coldplay-viva-la-vida-mid",
                "downloadUrl": "/uploads/24946.mid",
                "fileSize": 12345,
            },
            {
                "id": 85261,
                "name": "Pirates of the Caribbean.mid",
                "slug": "pirates-mid",
                "url": "/pirates-mid",
                "downloadUrl": "/uploads/85261.mid",
            },
        ]
    }
}


async def test_bitmidi_parses_json_api():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=BITMIDI_JSON)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BitMidiSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert "/api/midi/all" in captured["url"]
    assert len(results) == 2
    assert results[0].source == MusicSource.BITMIDI
    # Relative downloadUrl gets absolutized to the bitmidi host.
    assert results[0].download_url == "https://bitmidi.com/uploads/24946.mid"
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


async def test_musescore_swallows_403():
    """Cloudflare blocks generic UAs; we must degrade gracefully."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = MuseScoreSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert results == []


# ---------- Bilibili ----------

BILI_API_PAGE_1 = {
    "data": {
        "result": [
            {
                "result_type": "video",
                "data": [
                    {
                        "bvid": "BV1abc",
                        "title": '<em class="keyword">Twinkle</em> 原琴演奏',
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
    # Both bare <em> and <em class="keyword"> must be stripped.
    assert "<em" not in results[0].title and "</em>" not in results[0].title


async def test_bilibili_returns_empty_on_520_rate_limit():
    """Bilibili occasionally returns 520 under rate limit; must not crash."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(520, text="rate limited")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        searcher = BilibiliSearcher(client=client)
        results = await searcher.search("twinkle", limit=5)
    assert results == []
