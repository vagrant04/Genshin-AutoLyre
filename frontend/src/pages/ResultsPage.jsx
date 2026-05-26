import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { parseResource, uploadMidi } from "../api/client.js";
import ResourceCard from "../components/ResourceCard.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

const FILTERS = [
  { key: "all", label: "全部" },
  { key: "freemidi", label: "FreeMIDI" },
  { key: "bitmidi", label: "BitMIDI" },
  { key: "musescore", label: "MuseScore" },
  { key: "bilibili", label: "B站" },
];

export default function ResultsPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { query = "", results = [] } = location.state || {};
  const [filter, setFilter] = useState("all");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!location.state) navigate("/");
  }, [location.state, navigate]);

  const filtered = useMemo(
    () => (filter === "all" ? results : results.filter((r) => r.source === filter)),
    [filter, results]
  );

  async function handleSelect(result) {
    setBusy(true);
    setError(null);
    try {
      const data = await parseResource({
        result_id: result.id,
        download_url: result.download_url,
        title: result.title,
        source: result.source,
      });
      navigate("/tracks", { state: data });
    } catch (err) {
      setError(err.userMessage || "下载或解析失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const data = await uploadMidi(file);
      navigate("/tracks", { state: data });
    } catch (err) {
      setError(err.userMessage || "上传失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 pb-32">
      <header className="mb-6">
        <button onClick={() => navigate("/")} className="mb-3 text-sm text-slate-500 hover:text-slate-900">
          ← 重新搜索
        </button>
        <h1 className="text-2xl font-bold">"{query}" 的搜索结果</h1>
        <p className="text-sm text-slate-600">共 {results.length} 条</p>
      </header>

      <nav className="mb-5 flex gap-2 overflow-x-auto">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`shrink-0 rounded-full border px-3 py-1 text-sm ${
              filter === f.key
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 hover:border-slate-700"
            }`}
          >
            {f.label}
          </button>
        ))}
      </nav>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {busy && <LoadingSpinner label="正在解析 MIDI…" />}

      {!busy && (
        <div className="space-y-3">
          {filtered.map((r) => (
            <ResourceCard key={r.id} result={r} onSelect={handleSelect} />
          ))}
          {filtered.length === 0 && (
            <p className="py-12 text-center text-slate-500">
              没有结果，可尝试英文曲名或上传本地 MIDI。
            </p>
          )}
        </div>
      )}

      <div className="fixed bottom-0 left-0 right-0 border-t border-slate-200 bg-white px-4 py-3">
        <label className="mx-auto flex max-w-3xl cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed border-slate-300 py-2 text-sm hover:border-slate-700">
          上传本地 MIDI 文件
          <input
            type="file"
            accept=".mid,.midi"
            onChange={handleUpload}
            className="hidden"
          />
        </label>
      </div>
    </main>
  );
}
