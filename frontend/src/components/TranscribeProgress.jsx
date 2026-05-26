const STAGE_COPY = {
  queued: "排队中…",
  downloading: "正在下载音频…",
  transcribing: "正在识别音符（首次约 30 秒）…",
  parsing: "正在解析 MIDI…",
  done: "完成",
  error: "出错",
};

export default function TranscribeProgress({ job }) {
  if (!job) return null;
  const stage = job.stage;
  const copy = STAGE_COPY[stage] || stage;
  const isError = stage === "error";

  return (
    <div
      className={
        isError
          ? "mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
          : "mt-5 rounded-lg border border-slate-200 bg-white p-4 text-sm"
      }
    >
      <p className="mb-2 font-medium">{copy}</p>
      {!isError && (
        <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
          <div
            className={
              stage === "done"
                ? "h-2 w-full rounded-full bg-emerald-500"
                : "h-2 w-1/3 animate-pulse rounded-full bg-slate-700"
            }
          />
        </div>
      )}
      {isError && job.error && (
        <p className="mt-1 text-xs">{job.error}</p>
      )}
    </div>
  );
}
