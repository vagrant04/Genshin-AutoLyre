function highlightOutOfRange(line) {
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
      <span key={`oor-${key++}`} className="rounded bg-amber-200 px-1 text-amber-900">
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

export default function ScoreDisplay({ text }) {
  if (!text) {
    return <p className="text-slate-500">本版本暂无音符。</p>;
  }
  const lines = text.split("\n");
  return (
    <pre className="score-mono whitespace-pre-wrap text-base leading-relaxed">
      {lines.map((line, i) => (
        <div key={i}>{highlightOutOfRange(line)}</div>
      ))}
    </pre>
  );
}
