# Audio-to-MIDI Pipeline — Design Spec

**Status:** Approved (pending user review of this written doc)
**Date:** 2026-05-22
**Branch:** `feat/audio-to-midi`
**Feature:** Add a parallel audio-source flow that downloads / receives audio (mp3, m4a, mp4) from YouTube, Bilibili, NetEase, QQ Music, or local upload, transcribes it to MIDI with Spotify Basic Pitch, then feeds the resulting MIDI into the existing parse + arrange pipeline. The existing MIDI-search flow is preserved unchanged.

---

## Problem statement

The four MIDI search platforms (FreeMIDI, BitMIDI, MuseScore, Bilibili-as-MIDI-host) have small catalogs and frequent download failures. For most popular Chinese and global music, the user can find an audio recording (a YouTube cover, a Bilibili video, a NetEase track) but not a MIDI file. Transcribing that audio to MIDI on demand expands the practical catalog from "a few tens of thousands of public-domain pieces" to "anything someone has uploaded as audio."

The honest scope: this works well for **solo-piano covers**. It works poorly for full-mix pop. We target the former and surface a quality warning rather than pretending to solve the latter.

---

## Goal

A user on the search page can:

1. Toggle between **MIDI 搜索** mode (existing) and **音频搜索 / 上传** mode (new).
2. In audio mode, do one of:
   - **Upload** a local `.mp3` / `.m4a` / `.mp4` file.
   - **Paste a URL** (YouTube / Bilibili / NetEase / QQ) — the backend downloads the audio.
   - **Search by text** on a chosen platform — the backend returns candidate audio results, user picks one.
3. After selection, watch a progress indicator (download → transcribe).
4. End up on the existing TrackConfig page with a parsed MIDI ready for the rest of the lyre flow.

---

## Non-goals (deferred / out of scope)

- Async job queue (v1 is synchronous; one transcription per request, blocking).
- Fine-grained progress streaming (SSE / WebSockets). v1 shows indeterminate "正在下载 / 正在识别" stages.
- Source-rotation auto-fallback when one platform fails. We surface clean errors instead.
- Stems separation (vocal / drums isolation before transcription).
- Replacing the existing MIDI-search flow — it stays.

---

## Architecture

```
┌─ MIDI 搜索 (unchanged) ──────────┐
│  /api/search → /api/parse →     │
│  /api/generate                  │  ──┐
└─────────────────────────────────┘    │
                                       ├──→ Same TrackConfig + Score pages
┌─ 音频 (new) ─────────────────────┐    │
│  /api/audio/search              │    │
│  /api/audio/transcribe          │ ───┘
│    └─→ download → Basic Pitch   │
│        → /api/parse pipeline    │
└─────────────────────────────────┘
```

The audio path **terminates by feeding** the existing `_parse_and_save()` from `routes_parse.py`. The frontend then transitions to TrackConfig exactly as it does for MIDI search results. No changes to the arranger, formatter, or score pages.

---

## Backend changes

### New package: `backend/audio/`

```
audio/
├── __init__.py
├── sources/
│   ├── __init__.py
│   ├── base.py           # AbstractAudioSource: search() + fetch_to_path()
│   ├── youtube.py        # yt-dlp wrapper: YT URL + ytsearch:
│   ├── bilibili.py       # yt-dlp wrapper: Bilibili URL + bilisearch:
│   ├── netease.py        # pyncm wrapper (best-effort)
│   └── qqmusic.py        # qqmusic-api-python wrapper (best-effort)
├── transcriber.py        # Basic Pitch wrapper, lazy-loaded
└── progress.py           # callback-based progress reporter (used by frontend in v1.x)
```

**`AbstractAudioSource` interface:**

```python
class AudioCandidate(BaseModel):
    source: AudioSourceKey   # "youtube" | "bilibili" | "netease" | "qqmusic"
    candidate_id: str         # platform-specific id
    title: str
    artist: str | None
    duration_seconds: int | None
    thumbnail_url: str | None
    canonical_url: str        # what fetch_to_path will be given

class AbstractAudioSource(abc.ABC):
    source: AudioSourceKey

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[AudioCandidate]: ...

    @abstractmethod
    async def fetch_to_path(self, url: str, target: Path) -> AudioMetadata: ...
        # writes audio to `target`, returns metadata (title, duration, etc.)
```

**Per-source quirks:**

- `youtube.py` and `bilibili.py` use `yt-dlp` with format selection `bestaudio/best`. yt-dlp supports both URL extraction and `ytsearch5:query` / `bilisearch5:query` for search. Most reliable path.
- `netease.py` uses `pyncm`. Many tracks return only 30-second previews when not logged in, or are 403 outside China. We surface `SourceUnavailable` cleanly.
- `qqmusic.py` uses `qqmusic-api-python`. Same caveats as NetEase.
- All searchers swallow internal exceptions and return `[]` (matching the existing `BaseMusicSearcher` pattern in `search/base.py`).
- `fetch_to_path` raises `SourceUnavailable` when paywalled / region-blocked / API-broken. This maps to a clear user-facing error.

### Transcriber

```
audio/transcriber.py:
    _model = None  # module-level cache (Basic Pitch loads ~30s on first use)

    async def transcribe(
        audio_path: Path,
        midi_out_path: Path,
        *,
        onset_threshold: float = 0.5,
        min_note_length_ms: int = 60,
    ) -> Path:
        # Run Basic Pitch in a thread (it's CPU-bound + sync).
        # Returns the output path on success; raises TranscriptionError otherwise.
```

User-facing controls map to thresholds:

| UI label | onset_threshold | min_note_length_ms |
|----------|-----------------|--------------------|
| 灵敏度 低 | 0.7 (fewer notes) | — |
| 灵敏度 中 (default) | 0.5 | — |
| 灵敏度 高 (more notes) | 0.3 | — |
| 最短音符 (slider) | — | 30 – 200ms |

### New routes

#### `GET /api/audio/search`

Query params:

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `q` | string (≥1) | yes | search query |
| `platform` | enum | yes | `youtube` \| `bilibili` \| `netease` \| `qqmusic` |
| `limit` | int (1-20) | no, default 5 | per-source limit |

Response (200):

```json
{
  "query": "周杰伦 晴天",
  "platform": "bilibili",
  "total": 3,
  "candidates": [
    {
      "source": "bilibili",
      "candidate_id": "BV1xxx",
      "title": "晴天 piano cover",
      "artist": null,
      "duration_seconds": 250,
      "thumbnail_url": "https://i0.hdslb.com/.../cover.jpg",
      "canonical_url": "https://www.bilibili.com/video/BV1xxx"
    }
  ]
}
```

Errors: `SOURCE_UNAVAILABLE` (503) if the chosen platform's library throws.

#### `POST /api/audio/transcribe`

Request body — three input modes:

```json
// Mode A: URL paste
{
  "input_mode": "url",
  "url": "https://www.youtube.com/watch?v=...",
  "title": "Optional override",
  "onset_sensitivity": "medium",  // "low" | "medium" | "high"
  "min_note_ms": 60
}

// Mode B: upload (this is multipart/form-data with a "file" field
// and the same JSON fields as form fields)
{ "input_mode": "upload", ...same params }

// Mode C: search-result selection (pre-resolved candidate)
{
  "input_mode": "candidate",
  "source": "youtube",
  "canonical_url": "https://www.youtube.com/watch?v=...",
  "title": "...",
  ...
}
```

Backend pipeline:

1. Resolve the audio source. URL paste auto-detects platform from the host. `candidate` mode trusts the supplied source. Upload skips download.
2. Audio cache lookup: `/tmp/genshin_lyre/audio/{sha256(canonical_url)[:16]}.{ext}`. Skip download on hit.
3. Download via the chosen source. Enforce 50MB max and 10-minute max duration. Hard-fail with `AUDIO_TOO_LARGE` / `AUDIO_TOO_LONG`.
4. MIDI cache lookup: `/tmp/genshin_lyre/midi/transcribed/{sha256(canonical_url + onset + min_note)[:16]}.mid`. Skip transcription on hit.
5. Transcribe with Basic Pitch. Save to MIDI cache.
6. Hand the MIDI path to the existing `_parse_and_save()` (already exists in `routes_parse.py`; we extract it to a small shared helper or import it directly).
7. Return the same shape as `/api/parse`:

```json
{
  "file_token": "tmp_xxx",
  "title": "...",
  "bpm": 120,
  "ticks_per_beat": 480,
  "tracks": [...],
  "audio_meta": {
    "source": "youtube",
    "duration_seconds": 250,
    "transcription": { "onset_sensitivity": "medium", "min_note_ms": 60 }
  }
}
```

Response time: 15-45s typical (5s download + 10-30s transcribe + 2s parse). Frontend shows an indeterminate spinner with a 60s timeout.

### New error codes

```python
"AUDIO_DOWNLOAD_FAILED": (400, "音频下载失败"),
"AUDIO_TOO_LARGE": (400, "音频文件超过 50MB 限制"),
"AUDIO_TOO_LONG": (400, "音频时长超过 10 分钟限制"),
"TRANSCRIPTION_FAILED": (500, "音频转 MIDI 失败"),
"SOURCE_UNAVAILABLE": (503, "该平台接口当前不可用或歌曲需要付费，请换个歌曲或平台重试"),
"INVALID_AUDIO_URL": (400, "无法识别的音频 URL"),
```

### main.py changes

- Register `audio_router` alongside the existing routers.
- Create `/tmp/genshin_lyre/audio/` and `/tmp/genshin_lyre/midi/transcribed/` on startup.

### Dependencies (`backend/requirements.txt`)

```
yt-dlp==2024.10.22
basic-pitch==0.4.0
ffmpeg-python==0.2.0
pyncm==1.6.9.10
qqmusic-api-python==0.1.10
```

System dependency: `ffmpeg` binary on PATH. README updated.

Install size: ~1.5GB after installing TF + Basic Pitch model weights.

---

## Frontend changes

### Mode toggle on `SearchPage.jsx`

The existing search page gets a top-level toggle:

```
┌──────────────────────────────────┐
│ ⦿ MIDI 搜索  ◯ 音频搜索 / 上传    │
└──────────────────────────────────┘
```

**MIDI mode** is exactly what's there today (no changes).

**Audio mode** swaps the page body to the new `<AudioSearchSection>` component. The existing search history and results-page navigation are untouched.

### New component: `AudioSearchSection.jsx`

Three sub-sections:

1. **Upload card**: dropzone / file picker for `.mp3 / .m4a / .mp4`.
2. **URL paste card**: text input + submit button. Backend auto-detects platform from URL host.
3. **Search card**: query input + platform radio (YouTube / Bilibili / NetEase / QQ) + submit. Calls `/api/audio/search`, lists `<AudioCandidateCard>`s.
4. **Settings panel** (collapsible, "高级设置"): onset sensitivity radio + min note length slider.

### New component: `AudioCandidateCard.jsx`

```
┌──────────────────────────────────┐
│ [thumb] 晴天 piano cover          │
│         BV1xxx · 4:10 · Bilibili │
│                          [选择 →] │
└──────────────────────────────────┘
```

### New component: `TranscribeProgress.jsx`

Indeterminate two-stage progress bar:

```
正在下载音频… (~30 秒)         [#####...........]
正在识别音符…                  [..............]
```

Implementation: poll `/api/audio/transcribe` over the request lifetime; on completion, navigate to TrackConfig with the response state (same shape as MIDI parse output).

### `client.js` additions

```js
export async function searchAudio(query, platform, limit = 5) { ... }
export async function transcribeAudioUrl({ url, onsetSensitivity, minNoteMs }) { ... }
export async function transcribeAudioUpload(file, { onsetSensitivity, minNoteMs }) { ... }
export async function transcribeAudioCandidate(candidate, { onsetSensitivity, minNoteMs }) { ... }
```

All four return the same shape as the existing `parseResource` / `uploadMidi`, so the consumer code in `AudioSearchSection` can transition to TrackConfig with a single `navigate("/tracks", { state: data })` call.

### Files added / modified

```
backend/
  audio/                        NEW (entire package)
  api/routes_audio.py           NEW
  api/errors.py                 MODIFY (5 new codes)
  main.py                       MODIFY (register router + cache dirs)
  requirements.txt              MODIFY (5 new deps)
  tests/
    test_audio_sources.py       NEW (offline, mocked yt-dlp/pyncm)
    test_audio_transcriber.py   NEW (10s piano fixture, real Basic Pitch)
    test_routes_audio.py        NEW (route happy + error paths)
    fixtures/
      ten_seconds_piano.mp3     NEW (small CC0 piano clip)

frontend/
  src/
    pages/SearchPage.jsx        MODIFY (mode toggle)
    pages/AudioSearchPage.jsx   NEW (or render AudioSearchSection inside SearchPage)
    components/
      AudioModeToggle.jsx       NEW
      AudioSearchSection.jsx    NEW
      AudioCandidateCard.jsx    NEW
      TranscribeProgress.jsx    NEW
    api/client.js               MODIFY (4 new helpers)

README.md                       MODIFY (system deps, install size note, gray-area disclaimer)
```

---

## Testing strategy

### Backend

- **`test_audio_sources.py`** — mock `yt-dlp.YoutubeDL.extract_info` and write a fixture file to the target path. Verify each source returns the expected `AudioCandidate` shape and that errors are caught.
- **`test_audio_transcriber.py`** — real Basic Pitch transcription on a 10-second piano clip (committed fixture). Verifies the resulting MIDI has notes, BPM is plausible, parser can read it. Slow (~30s on first run due to TF lazy-load); markered `@pytest.mark.slow` and skipped in default CI but available locally.
- **`test_routes_audio.py`** — TestClient + mocked source `fetch_to_path`. Cases: URL paste happy path, upload happy path, candidate happy path, AUDIO_TOO_LARGE, SOURCE_UNAVAILABLE, INVALID_AUDIO_URL, TRANSCRIPTION_FAILED.
- **No live tests in default CI**. A separate `pytest -m audio_live` invocation can run end-to-end against real YouTube/Bilibili.

### Frontend

No automated tests (project has no Vitest). Manual QA checklist in the PR description.

---

## Caching strategy

Two on-disk caches under `/tmp/genshin_lyre/`:

| Path | Key | Eviction |
|------|-----|----------|
| `audio/{hash}.{ext}` | sha256(canonical_url)[:16] | Manual / restart wipes |
| `midi/transcribed/{hash}.mid` | sha256(canonical_url + onset + min_note)[:16] | Manual / restart wipes |

Re-running with different transcription params bypasses the MIDI cache (correctly) but reuses the audio cache (avoids re-download). Same params → instant return.

---

## Known risks and mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Install size jumps to ~1.5GB | Medium | README warning; consider optional extras in v2 |
| Basic Pitch first-call latency ~30s | Low | Show "正在初始化模型…" on the first transcription; subsequent are fast |
| NetEase/QQ libraries break or return paywalled stubs | High | Surface `SOURCE_UNAVAILABLE` cleanly; recommend YouTube/Bilibili for robust use |
| yt-dlp throttled by YouTube | Low | Cache aggressively; document a manual `yt-dlp -U` upgrade path |
| Transcription quality on full-mix songs | High | Document that solo-piano covers are the supported target; arpeggios and vocals will produce noise |
| Copyright posture | Medium | Personal-use disclaimer in the README; no public deployment |

---

## Open questions

None. Design fully decided in conversation.

---

## File-structure summary (delta only)

```
backend/
  audio/                          NEW package
    __init__.py                   NEW
    sources/__init__.py           NEW
    sources/base.py               NEW
    sources/youtube.py            NEW
    sources/bilibili.py           NEW
    sources/netease.py            NEW
    sources/qqmusic.py            NEW
    transcriber.py                NEW
    progress.py                   NEW (lightweight, no SSE in v1)
  api/
    routes_audio.py               NEW
    errors.py                     MODIFY (+5 codes)
  main.py                         MODIFY (+1 router, +2 cache dirs)
  requirements.txt                MODIFY (+5 deps)
  tests/
    test_audio_sources.py         NEW
    test_audio_transcriber.py     NEW
    test_routes_audio.py          NEW
    fixtures/ten_seconds_piano.mp3 NEW

frontend/
  src/
    pages/SearchPage.jsx          MODIFY (add mode toggle)
    components/AudioModeToggle.jsx     NEW
    components/AudioSearchSection.jsx  NEW
    components/AudioCandidateCard.jsx  NEW
    components/TranscribeProgress.jsx  NEW
    api/client.js                 MODIFY (+4 helpers)

README.md                         MODIFY
```
