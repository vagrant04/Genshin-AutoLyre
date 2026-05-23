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
