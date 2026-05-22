# Per-Track MIDI Preview — Design Spec

**Status:** Approved
**Date:** 2026-05-22
**Feature:** Listen to each parsed MIDI track on the TrackConfigPage before generating the lyre score, with a toggle between the raw original notes and the mapped lyre notes.

---

## Goal

On the TrackConfigPage, each track row exposes a play button. Clicking it streams that track's notes through an in-browser piano synth so the user can identify which track is the melody, verify the mapped lyre version sounds right, and compare against the original. Only one track plays at a time.

## Non-goals (deferred)

- "Play all selected" combined melody+accompaniment preview.
- Volume slider, tempo override, drag-to-scrub seek.
- Frontend automated tests (project has no Vitest setup yet — adding one is out of scope).

---

## Architecture

```
TrackConfigPage (existing)
   └─ TrackPanel (modified)
        ├─ activeTrackIndex state (only one row plays at a time)
        └─ for each track:
              ├─ row metadata (existing)
              ├─ play/stop button (new)
              └─ TrackTransport (new, mounted only when active)
                    ├─ useTrackPreview hook (new)
                    │     ├─ fetch /api/preview-track JSON (cached per key)
                    │     └─ drive piano.js
                    └─ piano.js (new singleton)
                          └─ Tone.Sampler + lazy-loaded piano samples
```

Backend exposes one new read-only endpoint that returns a flat list of notes with absolute millisecond timing. The endpoint is recomputed per request from the `ParsedMidi` already in `ParsedFileStore` — no new state, no caching server-side.

---

## Backend changes

### New endpoint: `GET /api/preview-track`

Query parameters:

| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `file_token` | string | yes | the token returned by `/api/parse` |
| `track_index` | int | yes | which track to preview |
| `mapped` | bool | yes | `true` → notes go through `mapper.note_mapper.map_notes()` first; `false` → original MIDI numbers from the parsed file |

Response (200):

```json
{
  "track_index": 0,
  "track_name": "Piano Right",
  "mapped": true,
  "bpm": 120,
  "ticks_per_beat": 480,
  "duration_ms": 12480,
  "notes": [
    {"midi": 60, "start_ms": 0, "duration_ms": 480, "velocity": 80},
    {"midi": 62, "start_ms": 480, "duration_ms": 480, "velocity": 78}
  ]
}
```

Errors (reuse existing catalog):
- `FILE_NOT_FOUND` (404) when `file_token` is unknown.
- `INVALID_TRACK_INDEX` (400) when `track_index` is not a valid track in the parsed file.

### Tick → millisecond conversion

New pure helper `backend/parser/timing.py`:

```python
def tick_to_ms(tick: int, *, ticks_per_beat: int, bpm: int) -> int:
    """Convert an absolute MIDI tick to milliseconds at a fixed BPM."""
```

Formula: `tick * 60_000 / (ticks_per_beat * bpm)`. We use the document-level BPM that the parser already extracts (spec §8.2.1 default 120). Mid-song tempo changes are not supported in v1 — they're rare in practice and would complicate timing without changing the "is this the melody?" UX outcome.

### Route implementation: `backend/api/routes_preview.py`

Implementation outline:
1. Look up `StoredRecord` by `file_token` (raise `FILE_NOT_FOUND` on KeyError).
2. Find the matching `ParsedTrack` by `track_index` (raise `INVALID_TRACK_INDEX` if absent).
3. If `mapped=true`: run `map_notes(track.notes)` and emit `(mapped_midi, start_tick, duration_tick, velocity)` for each — but **only for notes whose mapping fell within the legal lyre range**. Out-of-range/semitone-adjusted notes still play (using their adjusted MIDI value); we keep them since the goal is to preview what the lyre version will sound like.
4. If `mapped=false`: emit `(midi_num, start_tick, duration_tick, velocity)` directly from the parsed notes.
5. Convert ticks to ms with `tick_to_ms`.
6. `duration_ms = max(start_ms + duration_ms across notes)`.

### Wired into `main.py`

Register `routes_preview.router` alongside the existing search/parse/generate routers.

### Backend tests (`tests/test_routes_preview.py`)

- `test_preview_returns_mapped_notes` — token from fixture, track_index=0, mapped=true → notes have lyre-legal MIDI numbers (in `LEGAL_MIDI_SET`).
- `test_preview_returns_raw_notes` — same token, mapped=false → notes match the parsed track's original MIDI numbers exactly.
- `test_preview_unknown_token_returns_404` — error envelope with `error="FILE_NOT_FOUND"`.
- `test_preview_invalid_track_returns_400` — `error="INVALID_TRACK_INDEX"`.

Plus `tests/test_timing.py` with two unit tests:
- `test_tick_to_ms_basic` — tick=480, tpb=480, bpm=120 → 500ms.
- `test_tick_to_ms_zero_tick_is_zero_ms`.

---

## Frontend changes

### New file: `frontend/src/audio/piano.js`

Singleton Tone.js wrapper. The Sampler is created on first call to `play()` (so the page doesn't load Tone or fetch piano samples until the user actually clicks play). Exposes:

```js
async function play(notes, { onTick, onEnd, loop }): playback handle
function pause(): void
function resume(): void
function stop(): void
function seek(ms: number): void
```

`notes` is the JSON array from `/api/preview-track`. The function:
1. Calls `Tone.start()` if the audio context is suspended (must run in a user gesture — that's why `play` is fired from a click handler).
2. Lazy-imports `tone` (`const Tone = await import("tone")`) so the dev bundle stays small.
3. Builds a `Tone.Sampler` once with Salamander Grand Piano samples from `https://tonejs.github.io/audio/salamander/` (the CDN that Tone.js's own examples use). On Sampler load failure, falls back to a basic `Tone.Synth` (sine wave) and surfaces a "钢琴音色加载失败，使用合成音" warning via `onSamplerFallback` callback.
4. Schedules each note: `sampler.triggerAttackRelease(Tone.Frequency(n.midi, "midi"), n.duration_ms/1000, "+" + n.start_ms/1000, n.velocity/127)`.
5. Starts `Tone.Transport` and emits `onTick(currentMs)` every 50ms via `Tone.Transport.scheduleRepeat`.
6. When transport reaches `duration_ms`: if `loop`, seek to 0; else `onEnd()`.

### New file: `frontend/src/hooks/useTrackPreview.js`

Owns playback state for one track:

```js
const {
  isReady,        // notes fetched
  isPlaying,
  currentMs,
  durationMs,
  mode,           // 'mapped' | 'raw'
  loop,
  setMode,
  setLoop,
  play, pause, stop, seek,
  error,
} = useTrackPreview({ fileToken, trackIndex });
```

Internals:
- Fetches notes via `getPreviewTrack(fileToken, trackIndex, mode)` from `client.js`.
- Caches by `(fileToken, trackIndex, mode)` in a module-level `Map` so toggling mode or re-opening transport doesn't refetch.
- Subscribes to `piano.js` callbacks; calls `piano.stop()` on unmount.

### New file: `frontend/src/components/TrackTransport.jsx`

Renders the inline transport bar: play/pause button, time `0:12 / 0:42`, seek bar (click-to-seek; no drag in v1), loop toggle, mapped|raw segmented control. Pure presentational — receives all state from `useTrackPreview`.

### Modified: `frontend/src/components/TrackPanel.jsx`

- Adds an `activeTrackIndex` state at the panel level.
- Each row gets a small `▶` icon button next to the track metadata. Clicking it sets `activeTrackIndex = track.index`. If a different row was active, its `useTrackPreview` instance unmounts and stops automatically.
- When `activeTrackIndex === track.index`, render `<TrackTransport fileToken={...} trackIndex={...} />` below the row's existing content (above the role selector).
- Stop and unmount the active transport when the user clicks the play button on the same row again (toggle behavior).

### Modified: `frontend/src/api/client.js`

Add:

```js
export async function getPreviewTrack(fileToken, trackIndex, mapped) {
  const resp = await client.get("/api/preview-track", {
    params: { file_token: fileToken, track_index: trackIndex, mapped },
  });
  return resp.data;
}
```

### New dependency

`tone@^15.0.0` added to `frontend/package.json`. Approximate cost: ~150 KB gzipped, lazy-loaded only when the user first clicks play.

---

## Data flow (full sequence)

1. User on TrackConfigPage clicks ▶ on row 1.
2. `TrackPanel` sets `activeTrackIndex = 1`. Row 1 mounts `<TrackTransport fileToken=tmp_xxx trackIndex=1 />`.
3. `useTrackPreview` runs effect: `getPreviewTrack(token, 1, true)`. Backend returns 200 JSON with note list.
4. The hook stores notes, sets `isReady=true`, `durationMs=N`, then calls `piano.play(notes, { onTick, onEnd })`.
5. `piano.js` lazy-imports Tone, creates the Sampler if needed, schedules every note, starts the transport.
6. Every 50 ms, `onTick(ms)` updates the hook's `currentMs`. `TrackTransport` re-renders the seek bar.
7. User clicks the segmented control to switch from "Mapped" to "Raw":
   - `setMode('raw')` calls `piano.stop()`, fetches raw notes (cache miss first time, cache hit thereafter), and calls `piano.play()` again. Position resets to 0.
8. User clicks ▶ on row 2:
   - `TrackPanel` sets `activeTrackIndex = 2`. Row 1's `TrackTransport` unmounts → cleanup effect calls `piano.stop()` and the hook releases its callback registration.
   - Row 2 mounts a fresh `TrackTransport`. New fetch + play.
9. User clicks ▶ on row 2 a second time → toggle behavior: `activeTrackIndex = null`, `TrackTransport` unmounts, `piano.stop()`.

---

## Error handling

| Failure | Behavior |
|---------|----------|
| Audio context suspended (Safari first-load) | `Tone.start()` invoked inside the click handler; if it still fails, transport shows "请再次点击开始播放". |
| `/api/preview-track` returns 404 / 400 | Hook surfaces `error` text; `TrackTransport` renders red "无法预览：{message}" instead of the play bar. |
| Sampler sample load fails | Synth fallback (sine wave); a small "钢琴音色加载失败，使用合成音" notice appears in the transport. |
| User navigates away while playing | TrackPanel's unmount calls `piano.stop()`. |

---

## Testing

### Backend

New file `tests/test_routes_preview.py` (4 cases) and `tests/test_timing.py` (2 cases). Together they verify happy paths for both modes, both error paths, and the timing helper boundary conditions. Run with the existing `pytest` command.

### Frontend

No automated tests in v1 — the project has no Vitest harness today, and bringing one in is its own piece of work. Manual QA checklist:

- [ ] Click ▶ on each track of the Twinkle fixture; piano plays.
- [ ] Toggle "Mapped" vs "Raw" — Mapped notes stay within the lyre range; Raw plays the original (e.g. bass track plays C2/F2/G2 in Raw, gets shifted up in Mapped).
- [ ] Click ▶ on a second row → first stops automatically.
- [ ] Click loop → reaches end → restarts.
- [ ] Click on the seek bar → playback jumps.
- [ ] Click ▶ then immediately ⏸ → no audio glitch, time freezes.
- [ ] Disable network after first load → piano-sample CDN unavailable on a fresh session: synth-fallback warning appears, playback still works.

---

## File structure summary

```
backend/
  api/
    routes_preview.py           NEW  — /api/preview-track route
  parser/
    timing.py                   NEW  — tick_to_ms helper
  main.py                       MODIFY — register preview router
  tests/
    test_routes_preview.py      NEW
    test_timing.py              NEW

frontend/
  package.json                  MODIFY — add tone dep
  src/
    api/
      client.js                 MODIFY — getPreviewTrack helper
    audio/
      piano.js                  NEW  — Tone.js singleton wrapper
    hooks/
      useTrackPreview.js        NEW  — per-track playback hook
    components/
      TrackTransport.jsx        NEW  — inline transport bar
      TrackPanel.jsx            MODIFY — play button + active-row state
```

---

## Open risks

1. **Tone.Sampler CDN dependency.** If `tonejs.github.io` is unreachable from a user's network, the synth fallback kicks in. Acceptable for a personal-use tool; document in README.
2. **Long pieces (~5 min).** Tone.Transport schedules every note up front. For ~5000 notes this is fine; verified in early Tone.js docs. If a user uploads a piano concerto with 50k notes we'd schedule them all and could see latency. Out of scope to optimize for now — the parser already drops anything < 30 ticks.
3. **Bilibili/MuseScore download flows are unrelated to this feature** — preview only depends on parsed data, which we already have for any successfully-parsed file.
