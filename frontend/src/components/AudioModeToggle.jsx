const MODES = [
  { value: "midi", label: "MIDI 搜索" },
  { value: "audio", label: "音频搜索 / 上传" },
];

export default function AudioModeToggle({ value, onChange }) {
  return (
    <div className="mb-6 inline-flex rounded-full border border-slate-300 bg-white p-1 text-sm">
      {MODES.map((m) => (
        <button
          key={m.value}
          type="button"
          onClick={() => onChange(m.value)}
          className={
            value === m.value
              ? "rounded-full bg-slate-900 px-4 py-1.5 text-white shadow-sm"
              : "rounded-full px-4 py-1.5 text-slate-600 hover:text-slate-900"
          }
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
