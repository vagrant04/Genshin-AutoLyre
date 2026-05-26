import { useState } from "react";

export default function SearchBar({ onSubmit, initialValue = "" }) {
  const [value, setValue] = useState(initialValue);

  function handleSubmit(e) {
    e.preventDefault();
    const q = value.trim();
    if (q.length === 0) return;
    onSubmit(q);
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="请输入曲名，如：小星星、Canon in D"
        className="flex-1 rounded-lg border border-slate-300 px-4 py-3 text-base focus:border-slate-700 focus:outline-none"
      />
      <button
        type="submit"
        className="rounded-lg bg-slate-900 px-6 py-3 text-base text-white hover:bg-slate-700"
      >
        搜索
      </button>
    </form>
  );
}
