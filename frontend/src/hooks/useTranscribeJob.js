import { useEffect, useRef, useState } from "react";
import { getAudioJob } from "../api/client.js";

const POLL_INTERVAL_MS = 700;
const TIMEOUT_MS = 120_000;

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
          // 404 means the server forgot the job (e.g. it restarted).
          // Surface a clearer message than the generic "轮询失败".
          const msg = err.response?.status === 404
            ? "任务已丢失（服务器可能重启），请重新提交。"
            : (err.userMessage || "轮询失败");
          setJob({
            stage: "error",
            error: msg,
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
