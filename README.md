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
