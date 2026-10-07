import { useState, useEffect } from "react";
import type { ReactNode } from "react";
import type { Run, Result } from "../types";
import { OFFICIAL_MODES, modeEntries, modeKey, modeLabel, ThinkingComparison } from "./ThinkingComparison";
import { ResourceMetrics } from "./ResourceMetrics";
import { SamplingInput } from "./SamplingInput";
import { InputConfiguration } from "./InputConfiguration";

export function CaptionPanel({ entries, run, value, task, camera, review, selectRun, experimentProgress }: {
  entries: {run: Run; value: Result | undefined}[];
  run?: Run;
  value?: Result;
  task: string;
  camera: string;
  review: (camera: string, run: string) => void;
  selectRun: (run: string) => void;
  experimentProgress?: ReactNode;
}) {
  const [compare, setCompare] = useState(false);
  useEffect(()=>setCompare(false),[task]);
  const official = modeEntries(entries);
  const canCompare = official.some(entry => modeKey(entry.run) === "off")
    && official.some(entry => modeKey(entry.run) !== "off");
  const structured = Boolean(value?.annotation && typeof value.annotation === "object"
    && ["actions", "entities", "state_changes", "uncertainties"].some(key => Array.isArray((value.annotation as Record<string, unknown>)[key])));
  function showComparison() {
    if (run && modeKey(run) === "off") {
      const target = official.find(entry => modeKey(entry.run) === "medium")
        || official.find(entry => modeKey(entry.run) !== "off");
      if (target) selectRun(target.run.id);
    }
    setCompare(true);
  }
  return <article className="model-caption caption-panel">
    {official.length > 0 && <div className="caption-mode-controls">
      <div className="control-group" role="group" aria-label="思考模式">
        <span className="control-label">思考模式</span>
        <div className="segmented-controls">
          {official.map(entry => <button key={entry.run.id}
            aria-label={`选择思考模式 ${modeKey(entry.run)}`}
            aria-pressed={run?.id === entry.run.id}
            title={modeLabel(entry.run)}
            onClick={() => {
              selectRun(entry.run.id);
              if (modeKey(entry.run) === "off") setCompare(false);
            }}>{modeLabel(entry.run)}</button>)}
        </div>
      </div>
      {canCompare && <div className="control-group" role="group" aria-label="查看方式">
        <span className="control-label">查看方式</span>
        <div className="segmented-controls">
          <button aria-pressed={!compare} onClick={() => setCompare(false)}>单组</button>
          <button aria-pressed={compare} onClick={showComparison}>并排</button>
        </div>
      </div>}
    </div>}
    {experimentProgress}
    {compare && canCompare ? <ThinkingComparison entries={entries} camera={camera}
      review={review} task={task} selectedEffort={run ? modeKey(run) : "medium"}/>
    : <div className="model-output" key={`${camera}/${run?.id}`}>
      <p className="caption-text">{value?.caption_status === "success" ? value.generated_caption
        : value?.caption_status === "failed" ? `生成失败：${value.error || "请重试"}`
        : run?.camera && run.camera !== camera ? "此模型尚未生成该相机结果；请选择 camera2。" : "此片段尚未生成 caption。"}</p>
      {structured
        && <details><summary>结构化结果</summary><pre>{JSON.stringify(value?.annotation, null, 2)}</pre></details>}
      {value?.caption_status === "success" && <details className="caption-details"><summary>资源效率</summary><ResourceMetrics value={value}/></details>}
      <SamplingInput run={run?.id} task={task} result={value?.result_id} compact
        configuration={<InputConfiguration run={run}/>}/>
      {value?.caption_status === "success" && run && <button className="caption-review-button" onClick={() => review(camera, run.id)}>评价此结果</button>}
    </div>}
  </article>;
}
