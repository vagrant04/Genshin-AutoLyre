import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { searchMusic } from "../api/client.js";
import SearchBar from "../components/SearchBar.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

const HISTORY_KEY = "lyre.searchHistory";

function readHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function pushHistory(query) {
  const cur = readHistory().filter((q) => q !== query);
  cur.unshift(query);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(cur.slice(0, 10)));
}

export default function SearchPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState(readHistory());

  async function handleSearch(query) {
    setLoading(true);
    setError(null);
    try {
      const data = await searchMusic(query);
      pushHistory(query);
      setHistory(readHistory());
      navigate("/results", { state: { query, results: data.results } });
    } catch (err) {
      setError(err.userMessage || "搜索失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="mb-2 text-3xl font-bold">原神原琴 AI 编谱</h1>
      <p className="mb-8 text-slate-600">输入曲名，自动生成三版可弹奏琴谱。</p>
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
    </main>
  );
}
