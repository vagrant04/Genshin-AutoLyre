# 原神原琴 AI 编谱

Python (FastAPI) + React full-stack tool that searches for MIDI files
across four platforms, parses them, and produces three lyre arrangements
(melody-only, simplified accompaniment, full accompaniment) ready to
play in Genshin Impact's Windsong Lyre.

## Quick start

### Backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

App: http://localhost:5173

### Tests

```bash
cd backend && .venv/bin/python -m pytest -v
```

## System dependencies

- **ffmpeg** must be on your `PATH`. The audio pipeline uses it to decode `.mp3` / `.m4a` / `.mp4` audio before transcription.
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`.

## Install footprint

The Python backend installs ~1.5 GB of dependencies because of TensorFlow + the Spotify Basic Pitch model used for audio→MIDI transcription. The first transcription request also lazy-loads the model (~30 s on CPU); subsequent requests are fast.

If you only want MIDI search and don't need audio transcription, you can skip installing `basic-pitch` and `yt-dlp`; the audio routes will return errors cleanly and the rest of the app works.

## Scope and disclaimers

- **Solo-piano covers transcribe well.** Full-mix recordings (vocals + drums + bass) produce noisy transcriptions; you'll likely have to delete most accompaniment tracks on the TrackConfig page.
- **Personal-use only.** This tool downloads audio from third-party platforms (YouTube, Bilibili, QQ Music). Don't deploy it as a public service.
- **QQ Music is best-effort.** Most tracks are paywalled or geo-blocked; the integration uses an unofficial library that may break. YouTube and Bilibili are the most reliable sources.

## Architecture

- `backend/mapper/` — per-note mapping to lyre's 21 keys (no global transposition).
- `backend/arranger/` — three-version generation (chord reduction, conflict resolution, merging).
- `backend/parser/` — MIDI parsing, track classification, chord grouping.
- `backend/search/` — four platform searchers + async aggregator.
- `backend/formatter/` — PC + mobile score text generation.
- `backend/api/` — FastAPI routes (`/api/search`, `/api/parse`, `/api/upload`, `/api/generate`).
- `backend/utils/` — async download + URL-hash cache.
- `frontend/src/pages/` — Search → Results → TrackConfig → Score flow.

See `docs/superpowers/plans/` for the full implementation plans and
`requirements/genshin-lyre-requirements.md` for the original spec.

## Requirements

- Python 3.11+ (built and tested on 3.12)
- Node 18+ (built on 20)
