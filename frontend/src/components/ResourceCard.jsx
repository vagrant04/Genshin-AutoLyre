const SOURCE_LABELS = {
  freemidi: "FreeMIDI",
  bitmidi: "BitMIDI",
  musescore: "MuseScore",
  bilibili: "B站",
};

function truncate(text, n = 40) {
  return text.length > n ? text.slice(0, n - 1) + "…" : text;
}

export default function ResourceCard({ result, onSelect }) {
  const hasDownload = Boolean(result.download_url);
  const meta = [
    result.duration_seconds ? `${result.duration_seconds}s` : null,
    result.file_size_kb ? `${result.file_size_kb}KB` : null,
    result.track_count ? `${result.track_count} 轨道` : null,
  ].filter(Boolean);

  return (
    <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-start justify-between gap-3">
        <h3 className="text-base font-medium leading-tight">{truncate(result.title, 40)}</h3>
        <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {SOURCE_LABELS[result.source] || result.source}
        </span>
      </div>
      {meta.length > 0 && (
        <p className="mb-3 text-xs text-slate-500">{meta.join(" · ")}</p>
      )}
      {result.preview_keys && (
        <p className="mb-3 score-mono text-xs text-slate-700">{result.preview_keys}</p>
      )}
      <div className="flex justify-end">
        {hasDownload ? (
          <button
            onClick={() => onSelect(result)}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            选择此版本
          </button>
        ) : (
          <a
            href={result.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm hover:border-slate-700"
          >
            前往下载
          </a>
        )}
      </div>
    </article>
  );
}
