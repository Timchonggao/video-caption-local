import { useEffect } from "react";
import type { Clip } from "../types";
import { time } from "../types";
export function ClipStrip({
  clips,
  selected,
  select,
  available,
  onlyResults,
  setOnlyResults,
}: {
  clips: Clip[];
  selected: string;
  select: (id: string) => void;
  available: Set<string>;
  onlyResults: boolean;
  setOnlyResults: (checked: boolean) => void;
}) {
  const shown = onlyResults ? clips.filter(clip => available.has(clip.clip_id)) : clips;
  const filter = <label className="clip-result-filter"><input type="checkbox" checked={onlyResults}
    onChange={event => setOnlyResults(event.target.checked)} />仅看有结果</label>;
  useEffect(() => {
    document
      .querySelector(".clip-chip.active")
      ?.scrollIntoView({
        block: "nearest",
        inline: "nearest",
        behavior: "smooth",
      });
  }, [selected, onlyResults, shown.map(clip => clip.clip_id).join("|")]);
  return (
    <div className="clip-picker">
      <div className="strip-heading clip-strip-heading">
        <h2>
          选择片段{" "}
          <span className="clip-progress">
            {clips.findIndex((c) => c.clip_id === selected) + 1} /{" "}
            {clips.length}
          </span>
        </h2>
        <div>
          <button
            aria-label="向左浏览片段"
            onClick={() =>
              document
                .querySelector(".clip-strip")
                ?.scrollBy({ left: -280, behavior: "smooth" })
            }
          >
            ←
          </button>
          <button
            aria-label="向右浏览片段"
            onClick={() =>
              document
                .querySelector(".clip-strip")
                ?.scrollBy({ left: 280, behavior: "smooth" })
            }
          >
            →
          </button>
        </div>
      </div>
      <div className="clip-strip">
        {shown.map((c) => (
          <button
            key={c.clip_id}
            className={`clip-chip ${c.clip_id === selected ? "active" : ""}`}
            aria-pressed={c.clip_id === selected}
            onClick={() => select(c.clip_id)}
          >
            <strong>{c.clip_id.replace(/^sample_\d+_/, "")}</strong>
            <span>
              {time(c.clip_start_time_s)} — {time(c.clip_end_time_s)}
            </span>
            <small>{c.clip_duration_s.toFixed(1)} 秒</small>
          </button>
        ))}
        {!shown.length && <p className="empty">当前样本暂无此模型和相机的结果片段。</p>}
      </div>
      <div className="clip-filter-footer">{filter}</div>
    </div>
  );
}
