# Audio-to-MIDI Pipeline — Plan 3: React frontend + README

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the frontend audio mode that lives alongside the existing MIDI search. Users toggle to **音频搜索 / 上传** mode, drop a file or paste a URL or run a platform search, watch a polling progress UI as the backend transcribes, and land on the existing TrackConfig page once done. Plus README updates documenting the new system dependency (ffmpeg), install size, and personal-use scope.

**Architecture:** A new `<AudioModeToggle>` controls which body the existing `SearchPage.jsx` renders — current MIDI body or new `<AudioSearchSection>`. AudioSearchSection has three input cards (upload / URL / search) and a collapsible advanced-settings panel. Submitting any one calls `/api/audio/transcribe`, gets back a `job_token`, and renders `<TranscribeProgress>` which polls `/api/audio/jobs/{token}` every 700 ms. On `done`, it navigates to TrackConfig with the same router state shape the existing parse path produces.

**Tech Stack:** Same as the existing frontend — React 18, Vite, Tailwind, Axios, react-router-dom. No new npm dependencies.

---

## File structure (this plan)

```
frontend/
├── src/
│   ├── api/
│   │   └── client.js                      MODIFY (+5 helpers, +1 fetcher for parse-store re-hydration)
│   ├── components/
│   │   ├── AudioModeToggle.jsx            NEW
│   │   ├── AudioSearchSection.jsx         NEW (composes the three input cards + settings)
│   │   ├── AudioUploadCard.jsx            NEW
│   │   ├── AudioUrlCard.jsx               NEW
│   │   ├── AudioSearchCard.jsx            NEW
│   │   ├── AudioCandidateCard.jsx         NEW
│   │   ├── AudioAdvancedSettings.jsx      NEW
│   │   └── TranscribeProgress.jsx         NEW
│   ├── hooks/
│   │   └── useTranscribeJob.js            NEW (handles polling)
│   └── pages/
│       └── SearchPage.jsx                 MODIFY (add mode toggle + conditional body)
README.md                                   MODIFY (system deps, install size, scope notes)
```

**Responsibility split:**
- `AudioSearchSection` owns the orchestration: which input card is active, holds the advanced settings, dispatches transcribe requests, and renders progress.
- Each input card is presentational + handles its own validation. They emit `onSubmit({ mode, payload })` upward.
- `useTranscribeJob` hook owns the polling state machine — starts polling when given a `jobToken`, exposes `{stage, error, parseToken}`, stops on `done`/`error`/unmount.
- `TranscribeProgress` is pure presentation: receives stage + error, shows the right copy.

---

## Task 1: API client helpers

**Files:**
- Modify: `frontend/src/api/client.js`

- [ ] **Step 1: Append five helpers**

After the existing `getPreviewTrack` export in `frontend/src/api/client.js`, add:

```javascript
export async function searchAudio(query, platform, limit = 5) {
  const resp = await client.get("/api/audio/search", {
    params: { q: query, platform, limit },
  });
  return resp.data;
}

export async function transcribeAudioUrl({ url, title, onsetSensitivity, minNoteMs }) {
  const form = new FormData();
  form.append("input_mode", "url");
  form.append("url", url);
  if (title) form.append("title", title);
  form.append("onset_sensitivity", onsetSensitivity);
  form.append("min_note_ms", String(minNoteMs));
  const resp = await client.post("/api/audio/transcribe", form);
  return resp.data; // { job_token }
}

export async function transcribeAudioCandidate({ source, canonicalUrl, title, onsetSensitivity, minNoteMs }) {
  const form = new FormData();
  form.append("input_mode", "candidate");
  form.append("source", source);
  form.append("canonical_url", canonicalUrl);
  form.append("title", title);
  form.append("onset_sensitivity", onsetSensitivity);
  form.append("min_note_ms", String(minNoteMs));
  const resp = await client.post("/api/audio/transcribe", form);
  return resp.data;
}

export async function transcribeAudioUpload(file, { title, onsetSensitivity, minNoteMs }) {
  const form = new FormData();
  form.append("input_mode", "upload");
  form.append("file", file);
  form.append("title", title);
  form.append("onset_sensitivity", onsetSensitivity);
  form.append("min_note_ms", String(minNoteMs));
  const resp = await client.post("/api/audio/transcribe", form);
  return resp.data;
}

export async function getAudioJob(jobToken) {
  const resp = await client.get(`/api/audio/jobs/${jobToken}`);
  return resp.data;
}
```

The transcribe route accepts both JSON and multipart for non-upload modes (FastAPI's `Form()` will decode JSON bodies too); using FormData uniformly here keeps the three helpers symmetric.

- [ ] **Step 2: Build to verify the file parses**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`. No errors.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/api/client.js && git commit -m "feat(frontend): API client helpers for /api/audio/*"
```

---

## Task 2: AudioModeToggle component

**Files:**
- Create: `frontend/src/components/AudioModeToggle.jsx`

- [ ] **Step 1: Write the component**

```javascript
const MODES = [
  { value: "midi", label: "MIDI 搜索" },
  { value: "audio", label: "音频搜索 / 上传" },
];

export default function AudioModeToggle({ value, onChange }) {
  return (
    <div className="mb-6 inline-flex rounded-full border border-slate-300 bg-white p-1 text-sm">
      {MODES.map((m) => (
        <button
          key={m.value}
          type="button"
          onClick={() => onChange(m.value)}
          className={
            value === m.value
              ? "rounded-full bg-slate-900 px-4 py-1.5 text-white shadow-sm"
              : "rounded-full px-4 py-1.5 text-slate-600 hover:text-slate-900"
          }
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/components/AudioModeToggle.jsx && git commit -m "feat(frontend): AudioModeToggle component"
```

---

## Task 3: AudioAdvancedSettings component

**Files:**
- Create: `frontend/src/components/AudioAdvancedSettings.jsx`

The two transcription knobs surfaced to the user.

- [ ] **Step 1: Write the component**

```javascript
const SENSITIVITY = [
  { value: "low", label: "低 (更少音符)" },
  { value: "medium", label: "中" },
  { value: "high", label: "高 (更多音符)" },
];

export default function AudioAdvancedSettings({
  sensitivity,
  minNoteMs,
  onChange,
}) {
  return (
    <details className="mb-4 rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <summary className="cursor-pointer font-medium">高级设置</summary>
      <div className="mt-3 space-y-3">
        <div>
          <label className="mb-1 block text-xs text-slate-500">音符灵敏度</label>
          <div className="flex gap-2">
            {SENSITIVITY.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => onChange({ sensitivity: s.value, minNoteMs })}
                className={
                  sensitivity === s.value
                    ? "rounded-md bg-slate-900 px-3 py-1.5 text-xs text-white"
                    : "rounded-md border border-slate-300 px-3 py-1.5 text-xs hover:border-slate-700"
                }
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">
            最短音符 ({minNoteMs} ms)
          </label>
          <input
            type="range"
            min="30"
            max="200"
            step="10"
            value={minNoteMs}
            onChange={(e) =>
              onChange({ sensitivity, minNoteMs: Number(e.target.value) })
            }
            className="w-full"
          />
        </div>
      </div>
    </details>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/components/AudioAdvancedSettings.jsx && git commit -m "feat(frontend): AudioAdvancedSettings panel"
```

---

## Task 4: AudioUploadCard, AudioUrlCard, AudioSearchCard

**Files:**
- Create: `frontend/src/components/AudioUploadCard.jsx`
- Create: `frontend/src/components/AudioUrlCard.jsx`
- Create: `frontend/src/components/AudioSearchCard.jsx`
- Create: `frontend/src/components/AudioCandidateCard.jsx`

Each input card emits `onSubmit({ mode, payload })`. Search additionally fetches its own candidate list and renders cards.

- [ ] **Step 1: Write `AudioUploadCard.jsx`**

```javascript
import { useState } from "react";

export default function AudioUploadCard({ onSubmit, disabled }) {
  const [file, setFile] = useState(null);

  function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    onSubmit({ mode: "upload", file });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-5"
    >
      <h2 className="mb-2 text-sm font-semibold text-slate-700">
        上传本地音频
      </h2>
      <p className="mb-3 text-xs text-slate-500">
        支持 mp3 / m4a / mp4 / wav / aac，最大 50 MB。
      </p>
      <input
        type="file"
        accept=".mp3,.m4a,.mp4,.wav,.aac,audio/*"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
        className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm hover:file:border-slate-700"
      />
      <button
        type="submit"
        disabled={!file || disabled}
        className="mt-3 rounded-md bg-slate-900 px-4 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        开始转写
      </button>
    </form>
  );
}
```

- [ ] **Step 2: Write `AudioUrlCard.jsx`**

```javascript
import { useState } from "react";

export default function AudioUrlCard({ onSubmit, disabled }) {
  const [url, setUrl] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    onSubmit({ mode: "url", url: trimmed });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-5"
    >
      <h2 className="mb-2 text-sm font-semibold text-slate-700">粘贴 URL</h2>
      <p className="mb-3 text-xs text-slate-500">
        支持 YouTube、Bilibili、网易云音乐、QQ 音乐链接。
      </p>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://www.bilibili.com/video/BV..."
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-700 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!url.trim() || disabled}
        className="mt-3 rounded-md bg-slate-900 px-4 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        开始转写
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Write `AudioCandidateCard.jsx`**

```javascript
function formatDuration(seconds) {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

const SOURCE_LABELS = {
  youtube: "YouTube",
  bilibili: "Bilibili",
  netease: "网易云",
  qqmusic: "QQ 音乐",
};

export default function AudioCandidateCard({ candidate, onSelect, disabled }) {
  const meta = [
    candidate.candidate_id,
    formatDuration(candidate.duration_seconds),
    SOURCE_LABELS[candidate.source] || candidate.source,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <article className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
      {candidate.thumbnail_url ? (
        <img
          src={candidate.thumbnail_url}
          alt=""
          className="h-12 w-20 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="h-12 w-20 shrink-0 rounded bg-slate-100" />
      )}
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-medium">{candidate.title}</h3>
        <p className="truncate text-xs text-slate-500">{meta}</p>
      </div>
      <button
        onClick={() => onSelect(candidate)}
        disabled={disabled}
        className="shrink-0 rounded-md bg-slate-900 px-3 py-1 text-xs text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        选择
      </button>
    </article>
  );
}
```

- [ ] **Step 4: Write `AudioSearchCard.jsx`**

```javascript
import { useState } from "react";
import { searchAudio } from "../api/client.js";
import AudioCandidateCard from "./AudioCandidateCard.jsx";

const PLATFORMS = [
  { value: "youtube", label: "YouTube" },
  { value: "bilibili", label: "Bilibili" },
  { value: "netease", label: "网易云" },
  { value: "qqmusic", label: "QQ 音乐" },
];

export default function AudioSearchCard({ onSelectCandidate, disabled }) {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState("youtube");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [candidates, setCandidates] = useState([]);

  async function handleSearch(e) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    setBusy(true);
    setError(null);
    setCandidates([]);
    try {
      const data = await searchAudio(q, platform);
      setCandidates(data.candidates || []);
      if ((data.candidates || []).length === 0) {
        setError("未找到结果，请尝试其他关键词或平台。");
      }
    } catch (err) {
      setError(err.userMessage || "搜索失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="mb-2 text-sm font-semibold text-slate-700">
        在音乐平台搜索
      </h2>
      <form onSubmit={handleSearch} className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {PLATFORMS.map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => setPlatform(p.value)}
              className={
                platform === p.value
                  ? "rounded-full bg-slate-900 px-3 py-1 text-xs text-white"
                  : "rounded-full border border-slate-300 px-3 py-1 text-xs hover:border-slate-700"
              }
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="例如：晴天 piano cover"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-700 focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !query.trim()}
            className="rounded-md bg-slate-900 px-3 py-2 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            搜索
          </button>
        </div>
      </form>

      {error && (
        <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-800">
          {error}
        </p>
      )}

      {candidates.length > 0 && (
        <div className="mt-4 space-y-2">
          {candidates.map((c) => (
            <AudioCandidateCard
              key={`${c.source}-${c.candidate_id}`}
              candidate={c}
              onSelect={onSelectCandidate}
              disabled={disabled}
            />
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Build to verify all four parse and compile**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`.

- [ ] **Step 6: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/components/AudioUploadCard.jsx frontend/src/components/AudioUrlCard.jsx frontend/src/components/AudioSearchCard.jsx frontend/src/components/AudioCandidateCard.jsx && git commit -m "feat(frontend): four audio input cards (upload/url/search/candidate)"
```

---

## Task 5: useTranscribeJob hook

**Files:**
- Create: `frontend/src/hooks/useTranscribeJob.js`

- [ ] **Step 1: Write the hook**

```javascript
import { useEffect, useRef, useState } from "react";
import { getAudioJob } from "../api/client.js";

const POLL_INTERVAL_MS = 700;
const TIMEOUT_MS = 120_000; // 2 minutes hard cap

/**
 * Polls /api/audio/jobs/{token} every 700 ms until the job reaches
 * 'done' or 'error', then stops. Returns the latest job state + an
 * isPolling flag.
 */
export default function useTranscribeJob(jobToken) {
  const [job, setJob] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const cancelRef = useRef(false);

  useEffect(() => {
    if (!jobToken) {
      setJob(null);
      setIsPolling(false);
      return;
    }
    cancelRef.current = false;
    setIsPolling(true);
    const startedAt = Date.now();

    async function poll() {
      while (!cancelRef.current) {
        if (Date.now() - startedAt > TIMEOUT_MS) {
          setJob({
            stage: "error",
            error: "转写超时（>2 分钟），请重试或换一首。",
            parse_token: null,
          });
          setIsPolling(false);
          return;
        }
        try {
          const data = await getAudioJob(jobToken);
          if (cancelRef.current) return;
          setJob(data);
          if (data.stage === "done" || data.stage === "error") {
            setIsPolling(false);
            return;
          }
        } catch (err) {
          if (cancelRef.current) return;
          setJob({
            stage: "error",
            error: err.userMessage || "轮询失败",
            parse_token: null,
          });
          setIsPolling(false);
          return;
        }
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
      }
    }
    poll();
    return () => {
      cancelRef.current = true;
    };
  }, [jobToken]);

  return { job, isPolling };
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/hooks/useTranscribeJob.js && git commit -m "feat(frontend): useTranscribeJob polling hook"
```

---

## Task 6: TranscribeProgress component

**Files:**
- Create: `frontend/src/components/TranscribeProgress.jsx`

- [ ] **Step 1: Write the component**

```javascript
const STAGE_COPY = {
  queued: "排队中…",
  downloading: "正在下载音频…",
  transcribing: "正在识别音符（首次约 30 秒）…",
  parsing: "正在解析 MIDI…",
  done: "完成",
  error: "出错",
};

export default function TranscribeProgress({ job }) {
  if (!job) return null;
  const stage = job.stage;
  const copy = STAGE_COPY[stage] || stage;
  const isError = stage === "error";

  return (
    <div
      className={
        isError
          ? "mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          : "mt-5 rounded-lg border border-slate-200 bg-white p-4 text-sm"
      }
    >
      <p className="mb-2 font-medium">{copy}</p>
      {!isError && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className={
              stage === "done"
                ? "h-2 w-full rounded-full bg-emerald-500"
                : "h-2 w-1/3 animate-pulse rounded-full bg-slate-700"
            }
          />
        </div>
      )}
      {isError && job.error && (
        <p className="mt-1 text-xs">{job.error}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/components/TranscribeProgress.jsx && git commit -m "feat(frontend): TranscribeProgress polling UI"
```

---

## Task 7: AudioSearchSection — orchestrator component

**Files:**
- Create: `frontend/src/components/AudioSearchSection.jsx`

This composes the four input cards, advanced settings, transcribe dispatch, polling, and post-completion navigation.

When polling reaches `done`, we have a `parse_token` (the same kind `/api/parse` returns). The frontend doesn't currently re-fetch parse data — it carries it via router state. To stay symmetric, we add a small `getParseRecord(parseToken)` helper, but server-side we don't have a `GET /api/parse/{token}` endpoint. Two options:

1. Add `GET /api/parse/{token}` server-side. Cleanest.
2. Have `/api/audio/jobs/{token}` include the full parse response (tracks/bpm/etc.) when stage = done.

Option 2 is YAGNI-friendly — the server already has the parse record in memory. Let me update plan 2's job-status response *retroactively* by adding a small enhancement to the route in this plan.

Actually, simpler: I'll have AudioSearchSection navigate to TrackConfig with a *thin* state and let TrackConfig fetch the parse data. That requires Option 1 anyway.

**Cleanest path**: add `GET /api/parse/{token}` in this plan as a small backend addition (1 task), then the frontend uses it.

I'll insert that as Task 7a before this component.

- [ ] **Step 1: SKIP — task 7a comes first**

Skipping; complete after Task 7a below.

---

## Task 7a: Backend — add `GET /api/parse/{token}` to re-hydrate parse records

**Files:**
- Modify: `backend/api/routes_parse.py`
- Create: `backend/tests/test_routes_parse_get.py`

- [ ] **Step 1: Write a failing test**

```python
"""Tests for GET /api/parse/{token} — fetch a previously-saved parse record."""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from utils.cache import cache_path_for_url

FIXTURE = Path(__file__).parent / "fixtures" / "twinkle.mid"


def test_get_parse_record_returns_full_payload():
    fake_url = "https://example.com/parse-get-twinkle.mid"
    target = cache_path_for_url(fake_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, target)

    client = TestClient(app)
    parse_resp = client.post(
        "/api/parse",
        json={
            "result_id": "x",
            "download_url": fake_url,
            "title": "Twinkle",
        },
    )
    assert parse_resp.status_code == 200
    token = parse_resp.json()["file_token"]

    fetch_resp = client.get(f"/api/parse/{token}")
    assert fetch_resp.status_code == 200
    body = fetch_resp.json()
    assert body["file_token"] == token
    assert body["title"] == "Twinkle"
    assert body["bpm"] == 120
    assert len(body["tracks"]) == 3


def test_get_parse_record_unknown_returns_404():
    client = TestClient(app)
    resp = client.get("/api/parse/tmp_nope")
    assert resp.status_code == 404
    assert resp.json()["error"] == "FILE_NOT_FOUND"
```

- [ ] **Step 2: Confirm RED**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_routes_parse_get.py -v 2>&1 | tail -5`
Expected: 1 PASS (the 404 case), 1 FAIL (404 returned even on the valid token because route doesn't exist).

- [ ] **Step 3: Add the GET endpoint**

In `backend/api/routes_parse.py`, after the `upload` route, add:

```python
@router.get("/parse/{file_token}")
async def get_parse_record(
    file_token: str,
    store: ParsedFileStore = Depends(get_store),
) -> dict:
    try:
        record = store.get(file_token)
    except KeyError:
        raise make_error("FILE_NOT_FOUND", detail=file_token)
    return {
        "file_token": file_token,
        "title": record.title,
        "bpm": record.parsed.bpm,
        "ticks_per_beat": record.parsed.ticks_per_beat,
        "tracks": [t.model_dump(mode="json") for t in record.track_infos],
    }
```

- [ ] **Step 4: Verify GREEN**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest tests/test_routes_parse_get.py -v 2>&1 | tail -5`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add backend/api/routes_parse.py backend/tests/test_routes_parse_get.py && git commit -m "feat(api): GET /api/parse/{token} for parse-record re-hydration"
```

- [ ] **Step 6: Add a frontend client helper**

In `frontend/src/api/client.js`, after `getAudioJob`, add:

```javascript
export async function getParseRecord(parseToken) {
  const resp = await client.get(`/api/parse/${parseToken}`);
  return resp.data; // { file_token, title, bpm, ticks_per_beat, tracks }
}
```

- [ ] **Step 7: Build + commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5
```

Expected: `✓ built in ...`.

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/api/client.js && git commit -m "feat(frontend): getParseRecord client helper"
```

---

## Task 7b: AudioSearchSection — orchestrator component

**Files:**
- Create: `frontend/src/components/AudioSearchSection.jsx`

- [ ] **Step 1: Write the component**

```javascript
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getParseRecord,
  transcribeAudioCandidate,
  transcribeAudioUpload,
  transcribeAudioUrl,
} from "../api/client.js";
import useTranscribeJob from "../hooks/useTranscribeJob.js";
import AudioAdvancedSettings from "./AudioAdvancedSettings.jsx";
import AudioSearchCard from "./AudioSearchCard.jsx";
import AudioUploadCard from "./AudioUploadCard.jsx";
import AudioUrlCard from "./AudioUrlCard.jsx";
import TranscribeProgress from "./TranscribeProgress.jsx";

export default function AudioSearchSection() {
  const navigate = useNavigate();
  const [settings, setSettings] = useState({
    sensitivity: "medium",
    minNoteMs: 60,
  });
  const [jobToken, setJobToken] = useState(null);
  const [submitError, setSubmitError] = useState(null);

  const { job, isPolling } = useTranscribeJob(jobToken);

  // When the job completes, fetch the parse record and navigate.
  useEffect(() => {
    if (!job || job.stage !== "done" || !job.parse_token) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getParseRecord(job.parse_token);
        if (!cancelled) {
          navigate("/tracks", { state: data });
        }
      } catch (err) {
        if (!cancelled) {
          setSubmitError(err.userMessage || "无法读取转写结果");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [job, navigate]);

  const busy = isPolling || (job && job.stage !== "done" && job.stage !== "error");

  async function handleSubmit(payload) {
    setSubmitError(null);
    try {
      let resp;
      if (payload.mode === "upload") {
        resp = await transcribeAudioUpload(payload.file, {
          title: payload.file.name,
          onsetSensitivity: settings.sensitivity,
          minNoteMs: settings.minNoteMs,
        });
      } else if (payload.mode === "url") {
        resp = await transcribeAudioUrl({
          url: payload.url,
          onsetSensitivity: settings.sensitivity,
          minNoteMs: settings.minNoteMs,
        });
      } else if (payload.mode === "candidate") {
        resp = await transcribeAudioCandidate({
          source: payload.candidate.source,
          canonicalUrl: payload.candidate.canonical_url,
          title: payload.candidate.title,
          onsetSensitivity: settings.sensitivity,
          minNoteMs: settings.minNoteMs,
        });
      } else {
        return;
      }
      setJobToken(resp.job_token);
    } catch (err) {
      setSubmitError(err.userMessage || "请求失败");
    }
  }

  return (
    <div>
      <p className="mb-3 text-xs text-slate-500">
        从音频提取 MIDI（仅适合钢琴独奏；其他乐器/混音的识别效果较差）。
      </p>
      <AudioAdvancedSettings
        sensitivity={settings.sensitivity}
        minNoteMs={settings.minNoteMs}
        onChange={setSettings}
      />
      <div className="space-y-3">
        <AudioUploadCard onSubmit={handleSubmit} disabled={busy} />
        <AudioUrlCard onSubmit={handleSubmit} disabled={busy} />
        <AudioSearchCard
          onSelectCandidate={(candidate) =>
            handleSubmit({ mode: "candidate", candidate })
          }
          disabled={busy}
        />
      </div>
      {submitError && (
        <p className="mt-4 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-800">
          {submitError}
        </p>
      )}
      <TranscribeProgress job={job} />
    </div>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/components/AudioSearchSection.jsx && git commit -m "feat(frontend): AudioSearchSection orchestrator (input cards + progress + nav)"
```

---

## Task 8: Wire AudioModeToggle into SearchPage

**Files:**
- Modify: `frontend/src/pages/SearchPage.jsx`

- [ ] **Step 1: Add mode state, toggle, and conditional body**

Open `frontend/src/pages/SearchPage.jsx`. Add two imports near the top:

```javascript
import AudioModeToggle from "../components/AudioModeToggle.jsx";
import AudioSearchSection from "../components/AudioSearchSection.jsx";
```

Inside the `SearchPage` function, add a `mode` state alongside the existing `loading` / `error` / `history`:

```javascript
const [mode, setMode] = useState("midi");
```

Then change the JSX. The existing structure renders `<SearchBar>`, `<LoadingSpinner>` (when loading), an error block, and the history. Wrap that body in a conditional. Replace the `<main>` body with:

```jsx
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold">原神原琴 AI 编谱</h1>
      <p className="mb-6 text-slate-600">输入曲名，自动生成三版可弹奏琴谱。</p>

      <AudioModeToggle value={mode} onChange={setMode} />

      {mode === "midi" ? (
        <>
          <SearchBar onSubmit={handleSearch} />

          {loading && (
            <LoadingSpinner label="正在同时搜索 FreeMIDI、BitMIDI、MuseScore、B站…" />
          )}
          {error && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
              {error}
            </div>
          )}

          {history.length > 0 && !loading && (
            <section className="mt-10">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                最近搜索
              </h2>
              <div className="flex flex-wrap gap-2">
                {history.map((q) => (
                  <button
                    key={q}
                    onClick={() => handleSearch(q)}
                    className="rounded-full border border-slate-300 px-3 py-1 text-sm hover:border-slate-700"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </section>
          )}
        </>
      ) : (
        <AudioSearchSection />
      )}
    </main>
```

- [ ] **Step 2: Build**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`.

- [ ] **Step 3: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add frontend/src/pages/SearchPage.jsx && git commit -m "feat(frontend): SearchPage mode toggle (MIDI search vs audio)"
```

---

## Task 9: README updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add system dependency, install size, and scope sections**

Open `README.md` and add the following sections after the existing "Quick start" section (i.e. before "Architecture"):

```markdown
## System dependencies

- **ffmpeg** must be on your `PATH`. The audio pipeline uses it to decode `.mp3` / `.m4a` / `.mp4` audio before transcription.
  - macOS: `brew install ffmpeg`
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to `PATH`.

## Install footprint

The Python backend installs ~1.5 GB of dependencies because of TensorFlow Lite (used by Spotify Basic Pitch for audio→MIDI transcription). The first transcription request also lazy-loads the model (~30 s on CPU); subsequent requests are fast.

If you only want MIDI search and don't need audio transcription, you can skip installing `basic-pitch` and `yt-dlp`; the audio routes will return `503` cleanly and the rest of the app works.

## Scope and disclaimers

- **Solo-piano covers transcribe well.** Full-mix recordings (vocals + drums + bass) produce noisy transcriptions; you'll likely have to delete most accompaniment tracks on the TrackConfig page.
- **Personal-use only.** This tool downloads audio from third-party platforms (YouTube, Bilibili, NetEase, QQ Music). Don't deploy it as a public service.
- **NetEase / QQ Music are best-effort.** Most tracks are paywalled or geo-blocked; the integration uses unofficial libraries that break occasionally. YouTube and Bilibili are the most reliable sources.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/i605225/Desktop/Genshin_Lyre && git add README.md && git commit -m "docs: README — system deps, install size, scope, disclaimers"
```

---

## Task 10: Manual end-to-end smoke test

**Files:**
- None (verification only).

- [ ] **Step 1: Restart the backend with the audio pipeline live**

Run: `pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1`

Then in `backend/`: `.venv/bin/uvicorn main:app --port 8000 --log-level info &`. Wait 3 seconds.

- [ ] **Step 2: Start the frontend dev server**

In another shell from `frontend/`: `npm run dev`. Open http://localhost:5173.

- [ ] **Step 3: Test MIDI mode unchanged**

In the browser, the page should default to MIDI mode and behave exactly as before. Run a search like "twinkle" and confirm results render.

- [ ] **Step 4: Test audio upload mode**

Click **音频搜索 / 上传**. Upload `backend/tests/fixtures/ten_seconds_piano.mp3`. Click 开始转写. Watch progress: queued → downloading (skipped for upload) → transcribing → parsing → done. The page should navigate to TrackConfig with the transcribed MIDI loaded.

If transcription is the first one of the session it'll take ~30 s for TF lazy-load. Subsequent transcriptions are fast.

- [ ] **Step 5: Test audio search mode**

Switch back to home, click 音频, run a search like "twinkle piano cover" against YouTube. Verify candidate cards render. (We don't have to fully transcribe — just verify the search-and-display path works.)

- [ ] **Step 6: Stop the servers**

Run: `pkill -f 'uvicorn main:app'` and Ctrl-C the `npm run dev`. No commit.

---

## Task 11: Final regression

**Files:**
- None (verification only).

- [ ] **Step 1: Full backend tests**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/backend && .venv/bin/python -m pytest -q 2>&1 | tail -3`
Expected: every test passes (existing + plan 1 + plan 2 + plan 3 backend additions).

- [ ] **Step 2: Frontend build**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre/frontend && npm run build 2>&1 | tail -5`
Expected: `✓ built in ...`.

- [ ] **Step 3: Verify all three plans show in the git log**

Run: `cd /Users/i605225/Desktop/Genshin_Lyre && git log --oneline feat/genshin-lyre..feat/audio-to-midi 2>/dev/null | head -40`
Expected: a sequence of commits covering plan 1 (deps + audio package), plan 2 (routes), and plan 3 (frontend + README), all on the `feat/audio-to-midi` branch.

The audio-to-MIDI feature is now end-to-end functional.

---

## What's NOT in any of the three plans (intentionally deferred to a polish pass)

- **AUDIO_TOO_LONG enforcement.** The 10-minute duration cap from the spec is not enforced. Adding a quick `ffprobe` check before transcription is ~1 task; defer until users actually upload long files.
- **Server-Sent Events progress.** Polling at 700 ms is fine for v1; SSE would be cleaner but adds complexity.
- **Stems separation** (Spleeter) before transcription. Would dramatically improve full-mix songs but adds ~600 MB of deps.
- **`audio_live` integration tests** that hit real platforms. Markered but not implemented.
- **Frontend automated tests.** Project still has no Vitest harness; manual QA is documented in Task 10.
