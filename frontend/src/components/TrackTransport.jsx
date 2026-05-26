import { useEffect, useRef } from "react";
import useTrackPreview from "../hooks/useTrackPreview.js";

function formatTime(ms) {
  const sec = Math.floor(ms / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function TrackTransport({ fileToken, trackIndex }) {
  const {
    mode,
    setMode,
    loop,
    setLoop,
    isLoading,
    isReady,
    isPlaying,
    currentMs,
    durationMs,
    error,
    play,
    pause,
    seek,
  } = useTrackPreview({ fileToken, trackIndex });

  const seekBarRef = useRef(null);

  useEffect(() => {
    // When we switch mode mid-playback the hook's effect refetches and
    // resets currentMs; if we were playing, restart automatically.
    if (isPlaying) play();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  function handleSeekClick(event) {
    const bar = seekBarRef.current;
    if (!bar || durationMs <= 0) return;
    const rect = bar.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    seek(Math.max(0, Math.min(1, ratio)) * durationMs);
  }

  if (error) {
    return (
      <div className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-800">
        无法预览：{error}
      </div>
    );
  }

  const progress = durationMs > 0 ? currentMs / durationMs : 0;

  return (
    <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <button
          onClick={isPlaying ? pause : play}
          disabled={!isReady}
          aria-label={isPlaying ? "暂停" : "播放"}
          className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700 disabled:bg-slate-300"
        >
          {isPlaying ? "❚❚" : "▶"}
        </button>

        <span className="score-mono text-xs text-slate-600">
          {formatTime(currentMs)} / {formatTime(durationMs)}
        </span>

        <div className="flex items-center gap-1 rounded-full bg-slate-200 p-0.5 text-xs">
          <button
            onClick={() => setMode("mapped")}
            className={`rounded-full px-2 py-0.5 ${
              mode === "mapped" ? "bg-white shadow-sm" : "text-slate-600"
            }`}
          >
            原琴音
          </button>
          <button
            onClick={() => setMode("raw")}
            className={`rounded-full px-2 py-0.5 ${
              mode === "raw" ? "bg-white shadow-sm" : "text-slate-600"
            }`}
          >
            原始音
          </button>
        </div>

        <button
          onClick={() => setLoop(!loop)}
          aria-label="循环"
          className={`rounded-md border px-2 py-0.5 text-xs ${
            loop
              ? "border-slate-900 bg-slate-900 text-white"
              : "border-slate-300 text-slate-600 hover:border-slate-700"
          }`}
        >
          ↻ {loop ? "循环中" : "循环"}
        </button>
      </div>

      <div
        ref={seekBarRef}
        onClick={handleSeekClick}
        className="h-2 cursor-pointer rounded-full bg-slate-200"
      >
        <div
          className="h-2 rounded-full bg-slate-700 transition-all"
          style={{ width: `${Math.min(100, progress * 100)}%` }}
        />
      </div>

      {isLoading && (
        <p className="mt-2 text-xs text-slate-500">正在加载音符…</p>
      )}
    </div>
  );
}
