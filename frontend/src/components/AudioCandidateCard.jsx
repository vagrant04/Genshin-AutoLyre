function formatDuration(seconds) {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = String(seconds % 60).padStart(2, "0");
  return `${m}:${s}`;
}

const SOURCE_LABELS = {
  youtube: "YouTube",
  bilibili: "Bilibili",
  qqmusic: "QQ 音乐",
};

export default function AudioCandidateCard({ candidate, onSelect, disabled }) {
  const meta = [
    candidate.candidate_id,
    formatDuration(candidate.duration_seconds),
    SOURCE_LABELS[candidate.source] || candidate.source,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <article className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-3">
      {candidate.thumbnail_url ? (
        <img
          src={candidate.thumbnail_url}
          alt=""
          className="h-12 w-20 shrink-0 rounded object-cover"
        />
      ) : (
        <div className="h-12 w-20 shrink-0 rounded bg-slate-100" />
      )}
      <div className="min-w-0 flex-1">
        <h3 className="truncate text-sm font-medium">{candidate.title}</h3>
        <p className="truncate text-xs text-slate-500">{meta}</p>
      </div>
      <button
        onClick={() => onSelect(candidate)}
        disabled={disabled}
        className="shrink-0 rounded-md bg-slate-900 px-3 py-1 text-xs text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        选择
      </button>
    </article>
  );
}
