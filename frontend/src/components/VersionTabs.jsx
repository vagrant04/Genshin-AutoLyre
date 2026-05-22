export default function VersionTabs({ versions, active, onSelect }) {
  return (
    <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
      {versions.map((v) => (
        <button
          key={v.version}
          onClick={() => onSelect(v.version)}
          className={`flex-1 rounded-md px-3 py-2 text-sm font-medium ${
            active === v.version
              ? "bg-white shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          {v.version_label}
        </button>
      ))}
    </div>
  );
}
