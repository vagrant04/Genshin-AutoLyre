import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { generateScore } from "../api/client.js";
import TrackPanel from "../components/TrackPanel.jsx";
import LoadingSpinner from "../components/LoadingSpinner.jsx";

export default function TrackConfigPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const initial = location.state || null;

  const [roles, setRoles] = useState(() =>
    initial
      ? Object.fromEntries(initial.tracks.map((t) => [String(t.index), t.suggested_role]))
      : {}
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!initial) navigate("/");
  }, [initial, navigate]);

  if (!initial) return null;

  const hasMelody = Object.values(roles).includes("melody");

  async function handleGenerate() {
    setBusy(true);
    setError(null);
    try {
      const data = await generateScore({
        file_token: initial.file_token,
        title: initial.title,
        track_roles: roles,
      });
      navigate("/score", {
        state: { score: data, fileToken: initial.file_token, tracks: initial.tracks },
      });
    } catch (err) {
      setError(err.userMessage || "生成失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 pb-32">
      <button onClick={() => navigate(-1)} className="mb-3 text-sm text-slate-500 hover:text-slate-900">
        ← 返回
      </button>
      <h1 className="mb-1 text-2xl font-bold">配置轨道</h1>
      <p className="mb-2 text-sm text-slate-600">
        {initial.title} · BPM {initial.bpm}
      </p>
      <p className="mb-6 text-xs text-slate-500">
        系统已自动识别轨道角色，您可根据实际情况调整。分解和弦伴奏将完整保留；柱式和弦在简化版中将自动精简为
        2~3 个关键音。
      </p>

      <TrackPanel
        tracks={initial.tracks}
        roles={roles}
        fileToken={initial.file_token}
        onChange={(idx, value) =>
          setRoles((prev) => ({ ...prev, [String(idx)]: value }))
        }
      />

      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}

      {busy && <LoadingSpinner label="正在生成三版琴谱…" />}

      <div className="fixed bottom-0 left-0 right-0 border-t border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <span className="text-xs text-slate-500">
            {hasMelody ? "已就绪" : "请至少指定一条主旋律轨道"}
          </span>
          <button
            onClick={handleGenerate}
            disabled={!hasMelody || busy}
            className="rounded-lg bg-slate-900 px-5 py-2.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            生成琴谱
          </button>
        </div>
      </div>
    </main>
  );
}
