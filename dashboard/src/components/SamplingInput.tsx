import { useEffect, useState } from "react";
import { getJSON } from "../api";
import type { SamplingEvidence } from "../types";
import type { ReactNode } from "react";
export function SamplingInput({
  run,
  task,
  result,
  compact = true,
  configuration,
}: {
  run?: string;
  task: string;
  result?: string;
  compact?: boolean;
  configuration?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SamplingEvidence | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    setData(null);
    setError("");
    if (!open || !run) return;
    const controller = new AbortController();
    const query = new URLSearchParams({ run, task });
    if (result) query.set("result", result);
    getJSON<SamplingEvidence>(`/api/sampling?${query}`, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError("采样输入尚未保存或无法读取。");
      });
    return () => controller.abort();
  }, [open, run, task, result, retry]);
  return (
    <details
      className="sampling-input"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>采样输入</summary>
      {open && configuration}
      {open &&
        (!run ? (
          <p>尚未准备采样输入。</p>
        ) : error ? (
          <p role="status">
            {error} <button onClick={() => setRetry((n) => n + 1)}>重试</button>
          </p>
        ) : !data ? (
          <p>正在读取采样输入…</p>
        ) : (
          <>
            {(!compact || data.status !== "result") && <p>
              {data.status === "missing"
                ? data.message
                : data.status === "prepared"
                  ? "已准备，尚未生成结果。"
                  : "该次结果关联的采样输入。"}
            </p>}
            {data.provider_sampling_known === false && <p>{compact
              ? `服务端未返回实际抽帧与处理尺寸；上传源片段 ${data.video_export?.source_dimensions.join("×")}（无音频）。`
              : `请求 ${data.requested_fps} fps；服务端实际采样帧与处理尺寸未返回。上传源片段 ${data.video_export?.source_dimensions.join("×")}，无音频；下方不伪装展示模型实际采样图。`}</p>}
            {!compact && data.source_evidence?.run_id && <p>{data.source_evidence_available === false ? "历史来源已清理；当前采样图与输入在本运行独立保存。" : `采样证据复用自：${data.source_evidence.run_id}`}</p>}
            {!compact && data.temporal_evidence && <details>
              <summary>视频输入时间映射：{data.temporal_evidence.real_frame_count} 个真实帧，末尾补帧 {data.temporal_evidence.padding_count} 个</summary>
              <p>补帧仅重复末尾画面，不是新增观察；模型时间标记按两帧分组并显示至 0.1 秒。</p>
              <pre>{JSON.stringify(data.temporal_evidence.groups, null, 2)}</pre>
            </details>}
            {Boolean(data.frames.length) && (
              <>
                <p>
                  共 {data.frames.length} 帧；时间相对当前原始片段起点。
                  {data.display_profile
                    ? "图片为抽帧的压缩展示副本，原始时间不变。"
                    : "图片为保存的高清抽帧，原始时间不变。"}
                </p>
                <div className="sampling-grid">
                  {data.frames.map((frame, i) => (
                    <figure key={`${data.input_id}/${i}`}>
                      <img
                        loading="lazy"
                        src={frame.url}
                        alt={`采样帧 ${i + 1}`}
                      />
                      <figcaption>
                        <strong>
                          帧 {i + 1} · {frame.relative_time_s.toFixed(3)} 秒
                        </strong>
                        {!compact && <><span>源视频 {frame.source_time_s.toFixed(3)} 秒</span>
                        <span>
                          目标 {frame.requested_relative_time_s.toFixed(3)} 秒 ·
                          偏差 {(frame.deviation_s * 1000).toFixed(1)} ms
                        </span>
                        {frame.processed_size && (
                          <span>模型输入 {frame.processed_size.join("×")}</span>
                        )}
                        {frame.duplicate_of !== null &&
                          frame.duplicate_of !== undefined && (
                            <span>
                              重复帧：与帧 {frame.duplicate_of + 1} 相同
                            </span>
                          )}
                        </>}
                      </figcaption>
                    </figure>
                  ))}
                </div>
              </>
            )}
          </>
        ))}
    </details>
  );
}
