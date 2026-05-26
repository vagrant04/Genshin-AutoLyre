/**
 * Singleton Tone.js wrapper for previewing MIDI tracks.
 *
 * Lazy-loads `tone` and the Salamander Grand Piano sample set on first
 * call to play(). Falls back to a simple Synth (sine wave) if the
 * sample CDN is unreachable.
 *
 * Spec: docs/superpowers/specs/2026-05-22-track-preview-design.md
 */

let _tone = null;          // imported Tone.js module
let _instrument = null;    // Sampler or Synth
let _instrumentReady = null; // Promise gating instrument creation
let _usingSynthFallback = false;
let _activePart = null;    // currently scheduled Tone.Part
let _activeTickerId = null;
let _activeOnTick = null;
let _activeOnEnd = null;
let _activeDurationMs = 0;
let _activeLoop = false;

const PIANO_BASE_URL = "https://tonejs.github.io/audio/salamander/";

async function ensureTone() {
  if (_tone) return _tone;
  _tone = await import("tone");
  return _tone;
}

async function ensureInstrument() {
  if (_instrument) return _instrument;
  if (_instrumentReady) return _instrumentReady;
  _instrumentReady = (async () => {
    const Tone = await ensureTone();
    try {
      const sampler = new Tone.Sampler({
        urls: {
          A1: "A1.mp3", A2: "A2.mp3", A3: "A3.mp3", A4: "A4.mp3", A5: "A5.mp3", A6: "A6.mp3",
          C2: "C2.mp3", C3: "C3.mp3", C4: "C4.mp3", C5: "C5.mp3", C6: "C6.mp3",
        },
        baseUrl: PIANO_BASE_URL,
        release: 1,
      }).toDestination();
      // Wait for samples to load. Tone's `Tone.loaded()` resolves when
      // every audio buffer in the graph is ready.
      await Tone.loaded();
      _instrument = sampler;
      return _instrument;
    } catch (err) {
      // Network/CDN failure → cheap synth so the page still works.
      console.warn("[piano] sampler unavailable, falling back to synth:", err);
      _usingSynthFallback = true;
      _instrument = new Tone.PolySynth(Tone.Synth).toDestination();
      return _instrument;
    }
  })();
  return _instrumentReady;
}

export function isUsingSynthFallback() {
  return _usingSynthFallback;
}

function clearActive() {
  if (_activePart) {
    _activePart.stop();
    _activePart.dispose();
    _activePart = null;
  }
  if (_activeTickerId !== null && _tone) {
    _tone.Transport.clear(_activeTickerId);
    _activeTickerId = null;
  }
  _activeOnTick = null;
  _activeOnEnd = null;
}

/**
 * Play a list of {midi, start_ms, duration_ms, velocity} notes.
 * Stops anything currently playing.
 */
export async function play(notes, { onTick, onEnd, loop = false } = {}) {
  const Tone = await ensureTone();
  // The audio context must be resumed inside a user gesture. The caller
  // (a click handler) is the gesture; calling Tone.start() here is safe.
  if (Tone.context.state !== "running") {
    await Tone.start();
  }
  const instrument = await ensureInstrument();

  stop();

  const partEvents = notes.map((n) => ({
    time: n.start_ms / 1000,
    midi: n.midi,
    duration: n.duration_ms / 1000,
    velocity: Math.max(0.05, Math.min(1, n.velocity / 127)),
  }));

  const part = new Tone.Part((time, ev) => {
    instrument.triggerAttackRelease(
      Tone.Frequency(ev.midi, "midi").toNote(),
      ev.duration,
      time,
      ev.velocity,
    );
  }, partEvents);
  part.start(0);

  const durationMs = notes.length
    ? Math.max(...notes.map((n) => n.start_ms + n.duration_ms))
    : 0;

  _activePart = part;
  _activeOnTick = onTick;
  _activeOnEnd = onEnd;
  _activeDurationMs = durationMs;
  _activeLoop = loop;

  // 50 ms ticks for the seek bar.
  _activeTickerId = Tone.Transport.scheduleRepeat((time) => {
    const ms = Tone.Transport.seconds * 1000;
    if (_activeOnTick) _activeOnTick(ms);
    if (ms >= durationMs) {
      if (_activeLoop) {
        Tone.Transport.seconds = 0;
        if (_activeOnTick) _activeOnTick(0);
      } else {
        stop();
        if (_activeOnEnd) _activeOnEnd();
      }
    }
  }, 0.05);

  Tone.Transport.seconds = 0;
  Tone.Transport.start();
}

export function pause() {
  if (!_tone) return;
  _tone.Transport.pause();
}

export function resume() {
  if (!_tone) return;
  if (_tone.Transport.state !== "started") {
    _tone.Transport.start();
  }
}

export function stop() {
  if (!_tone) return;
  _tone.Transport.stop();
  clearActive();
}

export function seek(ms) {
  if (!_tone) return;
  _tone.Transport.seconds = ms / 1000;
  if (_activeOnTick) _activeOnTick(ms);
}

export function setLoop(loop) {
  _activeLoop = loop;
}
