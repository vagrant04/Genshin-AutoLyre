import { useState } from "react";
import { searchAudio } from "../api/client.js";
import AudioCandidateCard from "./AudioCandidateCard.jsx";

const PLATFORMS = [
  { value: "youtube", label: "YouTube" },
  { value: "bilibili", label: "Bilibili" },
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
