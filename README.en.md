# Genshin Lyre AI Auto-Arranger

> English · [简体中文](./README.md)

A Python (FastAPI) + React tool that turns MIDI files or audio recordings into playable Windsong Lyre scores for *Genshin Impact*. It searches MIDI repositories, parses tracks, maps every note onto the lyre's 21-key layout, and produces three score versions side-by-side (melody-only, simplified accompaniment, full accompaniment).

## Highlights

- **MIDI search** across FreeMIDI, BitMIDI, MuseScore and Bilibili in parallel.
- **Audio → MIDI**: paste a YouTube / Bilibili / QQ Music URL, or upload a local mp3/m4a/mp4. Spotify Basic Pitch transcribes the audio (works best on solo-piano covers).
- **Track configuration**: automatic role detection (melody / accompaniment / bass / ignored). The track-config page lets you override roles and preview each track with a piano sampler — toggle between *lyre-mapped* and *original* notes.
- **Three score versions generated together**:
  - **Melody-only** — single-hand, beginner-friendly.
  - **Simplified accompaniment** — melody + chord-reduced accompaniment, the best single-player balance.
  - **Full accompaniment** — melody + every accompaniment note, useful as reference or for duets.
- **Three score views**: human-readable (bar-grouped), PC keyboard (single line), mobile keypad (single line). Whitespace encodes rhythm directly.

## Quick start

### Backend

You need Python 3.11+ (3.12 recommended) — install via [pyenv](https://github.com/pyenv/pyenv), Homebrew, your system package manager, or the [official installer](https://www.python.org/downloads/). The commands below assume `python` resolves to your installed 3.11+ interpreter.

```bash
cd backend
python -m venv .venv
source .venv/bin/activate         # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs: <http://localhost:8000/docs>

### Frontend

You need Node 18+ (20 recommended).

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

App: <http://localhost:5173>

### Tests

With the backend virtualenv activated:

```bash
cd backend
pytest -v
```

Slow tests (Basic Pitch model lazy-loads on first run, ~30 s):

```bash
pytest -m slow -v
```

## System dependencies

- **ffmpeg** must be on your `PATH`. The audio pipeline uses it to decode `.mp3` / `.m4a` / `.mp4` before transcription.
  - macOS: `brew install ffmpeg`
  - Debian / Ubuntu: `sudo apt install ffmpeg`
  - Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`.

## Install footprint

The backend pulls in roughly **1.5 GB** of dependencies, dominated by TensorFlow + the Spotify Basic Pitch model weights. The first transcription request lazy-loads the model (~30 s on CPU); later requests are fast.

If you only want MIDI search, you can skip installing `basic-pitch` and `yt-dlp`. The audio routes will return clean errors and everything else keeps working.

## Scope and disclaimers

- **Solo-piano covers transcribe well.** Full-mix recordings (vocals + drums + bass) produce noisy transcriptions; expect to delete most accompaniment tracks on the TrackConfig page.
- **Personal-use only.** This tool downloads audio from third-party platforms (YouTube, Bilibili, QQ Music). Don't deploy it as a public service.
- **QQ Music is best-effort.** Most tracks are paywalled or geo-blocked; the integration uses an unofficial library that may break when their API changes. YouTube and Bilibili are the most reliable sources.

## Architecture

- `backend/mapper/` — per-note mapping to the lyre's 21 legal keys (local octave shift only — no global transposition).
- `backend/arranger/` — three-version generation (chord reduction, 4-key simultaneous-limit resolution, merger).
- `backend/parser/` — MIDI parsing, track classification, chord grouping.
- `backend/search/` — four MIDI-platform searchers + async aggregator.
- `backend/formatter/` — rhythm-aware grid encoding (PC / mobile / human views).
- `backend/audio/` — audio sources (YouTube / Bilibili / QQ Music) + Basic Pitch transcriber + job orchestrator.
- `backend/api/` — FastAPI routes: `/api/search`, `/api/parse`, `/api/upload`, `/api/generate`, `/api/preview-track`, `/api/audio/*`.
- `backend/utils/` — async download + URL-hash cache.
- `frontend/src/pages/` — Search → Results → TrackConfig → Score flow.

Full design specs are in `docs/superpowers/specs/`, per-task implementation plans in `docs/superpowers/plans/`, and the original product requirements in `requirements/genshin-lyre-requirements.md`.

## Requirements

- Python 3.11+ (built and tested on 3.12)
- Node 18+ (tested on 20)
- ffmpeg 4+ (tested on 7.x)
