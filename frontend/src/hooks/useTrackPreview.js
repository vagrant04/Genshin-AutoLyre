import { useCallback, useEffect, useRef, useState } from "react";
import { getPreviewTrack } from "../api/client.js";
import * as piano from "../audio/piano.js";

// Module-level cache so toggling Mapped/Raw or re-opening the
// transport does not re-fetch.
const NOTE_CACHE = new Map();

function cacheKey(fileToken, trackIndex, mapped) {
  return `${fileToken}::${trackIndex}::${mapped ? "m" : "r"}`;
}

export default function useTrackPreview({ fileToken, trackIndex }) {
  const [mode, setMode] = useState("mapped"); // 'mapped' | 'raw'
  const [loop, setLoopState] = useState(false);
  const [notes, setNotes] = useState(null);
  const [durationMs, setDurationMs] = useState(0);
  const [currentMs, setCurrentMs] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      piano.stop();
    };
  }, []);

  const fetchNotes = useCallback(
    async (nextMode) => {
      const key = cacheKey(fileToken, trackIndex, nextMode === "mapped");
      if (NOTE_CACHE.has(key)) return NOTE_CACHE.get(key);
      setIsLoading(true);
      try {
        const data = await getPreviewTrack(
          fileToken,
          trackIndex,
          nextMode === "mapped",
        );
        NOTE_CACHE.set(key, data);
        return data;
      } finally {
        if (isMountedRef.current) setIsLoading(false);
      }
    },
    [fileToken, trackIndex],
  );

  // Load notes for the current mode whenever it changes.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchNotes(mode)
      .then((data) => {
        if (cancelled || !isMountedRef.current) return;
        setNotes(data.notes);
        setDurationMs(data.duration_ms);
        setCurrentMs(0);
      })
      .catch((err) => {
        if (cancelled || !isMountedRef.current) return;
        setError(err.userMessage || "无法预览此轨道");
      });
    return () => {
      cancelled = true;
    };
  }, [mode, fetchNotes]);

  const play = useCallback(async () => {
    if (!notes || notes.length === 0) return;
    try {
      setError(null);
      setIsPlaying(true);
      await piano.play(notes, {
        loop,
        onTick: (ms) => {
          if (isMountedRef.current) setCurrentMs(ms);
        },
        onEnd: () => {
          if (isMountedRef.current) {
            setIsPlaying(false);
            setCurrentMs(0);
          }
        },
      });
    } catch (err) {
      if (isMountedRef.current) {
        setIsPlaying(false);
        setError("音频初始化失败，请再次点击");
      }
    }
  }, [notes, loop]);

  const pause = useCallback(() => {
    piano.pause();
    setIsPlaying(false);
  }, []);

  const stop = useCallback(() => {
    piano.stop();
    setIsPlaying(false);
    setCurrentMs(0);
  }, []);

  const seek = useCallback(
    (ms) => {
      piano.seek(Math.max(0, Math.min(durationMs, ms)));
      setCurrentMs(ms);
    },
    [durationMs],
  );

  const setLoop = useCallback((next) => {
    setLoopState(next);
    piano.setLoop(next);
  }, []);

  return {
    mode,
    setMode,
    loop,
    setLoop,
    isLoading,
    isReady: notes !== null,
    isPlaying,
    currentMs,
    durationMs,
    error,
    play,
    pause,
    stop,
    seek,
  };
}
