import { useState } from "react";

export default function AudioUploadCard({ onSubmit, disabled }) {
  const [file, setFile] = useState(null);

  function handleSubmit(e) {
    e.preventDefault();
    if (!file) return;
    onSubmit({ mode: "upload", file });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-xl border border-slate-200 bg-white p-5"
    >
      <h2 className="mb-2 text-sm font-semibold text-slate-700">
        上传本地音频
      </h2>
      <p className="mb-3 text-xs text-slate-500">
        支持 mp3 / m4a / mp4 / wav / aac，最大 50 MB。
      </p>
      <input
        type="file"
        accept=".mp3,.m4a,.mp4,.wav,.aac,audio/*"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
        className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-md file:border file:border-slate-300 file:bg-white file:px-3 file:py-1.5 file:text-sm hover:file:border-slate-700"
      />
      <button
        type="submit"
        disabled={!file || disabled}
        className="mt-3 rounded-md bg-slate-900 px-4 py-1.5 text-sm text-white disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        开始转写
      </button>
    </form>
  );
}
