import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import VersionTabs from "../components/VersionTabs.jsx";
import ScoreDisplay from "../components/ScoreDisplay.jsx";

const MODES = [
  { key: "pc", label: "PC 字母谱" },
  { key: "mobile", label: "手机数字谱" },
];

export default function ScorePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const score = location.state?.score;
  const fileToken = location.state?.fileToken;
  const tracks = location.state?.tracks;

  useEffect(() => {
    if (!score) navigate("/");
  }, [score, navigate]);

  const [activeVersion, setActiveVersion] = useState("simplified");
  const [activeMode, setActiveMode] = useState("pc");
  const [statsOpen, setStatsOpen] = useState(false);

  const current = useMemo(
    () => score?.versions?.find((v) => v.version === activeVersion) || null,
    [score, activeVersion]
  );

  if (!score || !current) return null;

  const text = activeMode === "pc" ? current.pc_score : current.mobile_score;

  function handleCopy() {
    navigator.clipboard.writeText(text || "");
  }

  function handleDownload() {
    const blob = new Blob([text || ""], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${score.title}-${current.version_label}-${activeMode}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <header className="mb-5">
        <h1 className="text-2xl font-bold">{score.title}</h1>
        <p className="text-sm text-slate-600">
          BPM {score.bpm} · {score.versions.length} 个版本
        </p>
      </header>

      <VersionTabs
        versions={score.versions}
        active={activeVersion}
        onSelect={setActiveVersion}
      />

      <div className="mt-4 mb-3 flex gap-2">
        {MODES.map((m) => (
          <button
            key={m.key}
            onClick={() => setActiveMode(m.key)}
            className={`rounded-md px-3 py-1.5 text-sm ${
              activeMode === m.key
                ? "bg-slate-900 text-white"
                : "border border-slate-300 hover:border-slate-700"
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <ScoreDisplay text={text} />
      </section>

      <details
        className="mt-4 rounded-lg border border-slate-200 bg-white p-3 text-sm"
        open={statsOpen}
        onToggle={(e) => setStatsOpen(e.currentTarget.open)}
      >
        <summary className="cursor-pointer font-medium">统计信息</summary>
        <dl className="mt-3 grid grid-cols-2 gap-2 text-slate-700">
          {Object.entries(current.statistics).map(([k, v]) => (
            <div key={k} className="flex justify-between border-b border-slate-100 py-1">
              <dt className="text-slate-500">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </details>

      <div className="mt-5 flex flex-wrap gap-2">
        <button
          onClick={handleCopy}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          复制琴谱
        </button>
        <button
          onClick={handleDownload}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          下载为 .txt
        </button>
        <button
          onClick={() =>
            navigate("/tracks", {
              state: {
                file_token: fileToken,
                title: score.title,
                bpm: score.bpm,
                ticks_per_beat: score.ticks_per_beat,
                tracks: tracks ?? [],
              },
            })
          }
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          重新配置轨道
        </button>
        <button
          onClick={() => navigate("/")}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
        >
          重新搜索
        </button>
      </div>

      <p className="mt-8 text-center text-xs text-slate-400">
        本琴谱仅供个人游戏娱乐使用
      </p>
    </main>
  );
}
