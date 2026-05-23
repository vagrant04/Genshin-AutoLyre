const SENSITIVITY = [
  { value: "low", label: "低 (更少音符)" },
  { value: "medium", label: "中" },
  { value: "high", label: "高 (更多音符)" },
];

export default function AudioAdvancedSettings({
  sensitivity,
  minNoteMs,
  onChange,
}) {
  return (
    <details className="mb-4 rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <summary className="cursor-pointer font-medium">高级设置</summary>
      <div className="mt-3 space-y-3">
        <div>
          <label className="mb-1 block text-xs text-slate-500">音符灵敏度</label>
          <div className="flex gap-2">
            {SENSITIVITY.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => onChange({ sensitivity: s.value, minNoteMs })}
                className={
                  sensitivity === s.value
                    ? "rounded-md bg-slate-900 px-3 py-1.5 text-xs text-white"
                    : "rounded-md border border-slate-300 px-3 py-1.5 text-xs hover:border-slate-700"
                }
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">
            最短音符 ({minNoteMs} ms)
          </label>
          <input
            type="range"
            min="30"
            max="200"
            step="10"
            value={minNoteMs}
            onChange={(e) =>
              onChange({ sensitivity, minNoteMs: Number(e.target.value) })
            }
            className="w-full"
          />
        </div>
      </div>
    </details>
  );
}
