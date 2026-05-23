import { useState } from "react";

export default function AudioUrlCard({ onSubmit, disabled }) {
  const [url, setUrl] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    onSubmit({ mode: "url", url: trimmed });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-5"
    >
      <h2 className="mb-2 text-sm font-semibold text-slate-700">粘贴 URL</h2>
      <p className="mb-3 text-xs text-slate-500">
        支持 YouTube、Bilibili、QQ 音乐链接。
      </p>
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://www.bilibili.com/video/BV..."
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-700 focus:outline-none"
      />
      <button
        type="submit"
        disabled={!url.trim() || disabled}
        className="mt-3 rounded-md bg-slate-900 px-4 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        开始转写
      </button>
    </form>
  );
}
