const ROLE_OPTIONS = [
  { value: "melody", label: "主旋律" },
  { value: "accompaniment", label: "伴奏" },
  { value: "bass", label: "低音" },
  { value: "ignored", label: "忽略" },
];

const CHORD_TYPE_LABELS = {
  chordal: "柱式和弦",
  arpeggiated: "分解和弦",
  mixed: "混合",
  none: "",
};

export default function TrackPanel({ tracks, roles, onChange }) {
  return (
    <ul className="space-y-3">
      {tracks.map((track) => {
        const value = roles[String(track.index)] ?? track.suggested_role;
        const recommended = track.suggested_role;
        return (
          <li
            key={track.index}
            className="rounded-xl border border-slate-200 bg-white p-4"
          >
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <h3 className="text-sm font-medium">{track.name}</h3>
              <span className="text-xs text-slate-500">
                {track.note_count} 音 · {track.pitch_range}
              </span>
            </div>
            <p className="mb-3 score-mono text-xs text-slate-600">
              {track.preview_keys}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              {ROLE_OPTIONS.map((opt) => {
                const active = value === opt.value;
                const isRec = recommended === opt.value;
                return (
                  <label
                    key={opt.value}
                    className={`relative cursor-pointer rounded-full border px-3 py-1 text-sm ${
                      active
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-300 hover:border-slate-700"
                    }`}
                  >
                    <input
                      type="radio"
                      name={`role-${track.index}`}
                      value={opt.value}
                      checked={active}
                      onChange={() => onChange(track.index, opt.value)}
                      className="sr-only"
                    />
                    {opt.label}
                    {isRec && (
                      <span className="ml-1 rounded bg-amber-200 px-1 text-[10px] text-amber-900">
                        推荐
                      </span>
                    )}
                  </label>
                );
              })}
              {value === "accompaniment" && CHORD_TYPE_LABELS[track.chord_type] && (
                <span className="ml-1 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {CHORD_TYPE_LABELS[track.chord_type]}
                </span>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
