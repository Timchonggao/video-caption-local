import type { Run, Result } from "../types";
import { ResourceMetrics } from "./ResourceMetrics";
import { SamplingInput } from "./SamplingInput";
import { InputConfiguration } from "./InputConfiguration";

export type Entry = { run: Run; value: Result | undefined };
export const OFFICIAL_MODES = [
  { key: "off", label: "关闭思考" },
  { key: "low", label: "low · 轻度思考" },
  { key: "medium", label: "medium · 中等思考" },
  { key: "xhigh", label: "xhigh · 深度思考" },
];

export function officialSeedOne(entries: Entry[]): Entry[] {
  return OFFICIAL_MODES.flatMap((mode) => entries.filter((entry) =>
    entry.run.experiment_family === "official-qwen38-v2" &&
    entry.run.seed_index === 1 && entry.run.official_profile === mode.key));
}

export function modeKey(run: Run): string {
  return run.official_profile || run.thinking_comparison_role || (run.thinking ? "on" : "off");
}
export function modeLabel(run: Run): string {
  const mode=modeKey(run);
  return mode === "off" ? "关闭思考" : mode === "on" ? "开启思考" : mode;
}
export function modeEntries(entries: Entry[]): Entry[] {
  if (entries.some(e=>e.run.release_id === "v2_1")) {
    return ["off","low","medium","xhigh","on"].flatMap(mode=>entries.filter(e=>e.run.release_id === "v2_1" && modeKey(e.run) === mode));
  }
  return officialSeedOne(entries);
}

export function ThinkingComparison({ entries, camera, review, selectedEffort, task }: {
  entries: Entry[];
  camera: string;
  review: (camera: string, run: string) => void;
  selectedEffort: string;
  task: string;
}) {
  const candidates = modeEntries(entries);
  const enabled = candidates.filter(entry => modeKey(entry.run) !== "off");
  const current = enabled.find(entry => modeKey(entry.run) === selectedEffort) || enabled[0];
  const selected = [candidates.find(entry => modeKey(entry.run) === "off"), current];
  return <section aria-label="thinking 开关对照">
    <div className="cd-cards">{selected.map(entry => entry && <article className="cd-card" key={entry.run.id}>
      <h3>{modeLabel(entry.run)}</h3>
      <p className="comparison-caption">{entry.value?.caption_status === "failed"
        ? `生成失败：${entry.value.error || "输出未完成"}`
        : entry.value?.generated_caption || "此片段尚未生成 caption。"}</p>
      <details className="caption-details"><summary>资源效率</summary><ResourceMetrics value={entry.value}/></details>
      <SamplingInput run={entry.run.id} task={task} result={entry.value?.result_id}
        configuration={<InputConfiguration run={entry.run}/>}/>
      {entry.value?.caption_status === "success" && <button
        onClick={() => review(camera, entry.run.id)}>评价{modeKey(entry.run) === "off" ? "非思考" : "思考"}结果</button>}
    </article>)}</div>
  </section>;
}
