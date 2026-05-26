function highlightOutOfRange(line, keyPrefix = "") {
  // Replace [TOKEN] with a highlighted span; preserve everything else.
  const parts = [];
  const regex = /\[([^\]]+)\]/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = regex.exec(line)) !== null) {
    if (match.index > lastIndex) {
      parts.push(line.slice(lastIndex, match.index));
    }
    parts.push(
      <span
        key={`${keyPrefix}oor-${key++}`}
        className="rounded bg-amber-200 px-1 text-amber-900"
      >
        {match[1]}
      </span>
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < line.length) {
    parts.push(line.slice(lastIndex));
  }
  return parts;
}

export default function ScoreDisplay({ text, mode }) {
  if (!text) {
    return <p className="text-slate-500">本版本暂无音符。</p>;
  }
  const isSingleLine = mode === "pc" || mode === "mobile";

  if (isSingleLine) {
    // Render the raw text inline (no per-line <div> wrapper) so the
    // <pre>'s intrinsic width matches the full token stream. The
    // outer scroll container then provides horizontal scrolling when
    // the content exceeds the parent's width. `whitespace-pre` keeps
    // every space (which encodes rhythm) intact; `inline-block`
    // ensures the <pre> grows to its content rather than shrinking
    // to its parent.
    return (
      <div className="overflow-x-auto">
        <pre className="score-mono inline-block whitespace-pre text-base leading-relaxed">
          {highlightOutOfRange(text)}
        </pre>
      </div>
    );
  }

  // Human view: one bar per line. Allow natural wrapping if a bar is
  // long, but keep its internal spaces.
  const lines = text.split("\n");
  return (
    <pre className="score-mono whitespace-pre-wrap text-base leading-relaxed">
      {lines.map((line, i) => (
        <div key={i}>{highlightOutOfRange(line, `${i}-`)}</div>
      ))}
    </pre>
  );
}
