import { useEffect, useState } from "react";
import type { Data, Clip, Run, Result } from "../types";
import { officialSeedOne } from "./ThinkingComparison";
import { ResourceMetrics } from "./ResourceMetrics";
import { CDComparison } from "./CDComparison";
import { SamplingInput } from "./SamplingInput";
import { chooseRun } from "../resultAvailability";
import { CaptionPanel } from "./CaptionPanel";

export function normalizeSelection(value: string | null): string {
  return value && /^[A-Za-z0-9_-]+\.camera[0-5]$/.test(value)
    ? value
    : "v1.camera2";
}
function hasStructuredContent(annotation: unknown) {
  return Boolean(
    annotation &&
      typeof annotation === "object" &&
      ["actions", "state_changes", "uncertainties", "entities"].some((key) =>
        Array.isArray((annotation as Record<string, unknown>)[key]),
      ),
  );
}
function ModelCaption({
  data,
  clip,
  label,
  entries,
  camera,
  review,
  selectedRun,
  selectRun,
}: {
  data: Data;
  clip: Clip;
  label: string;
  entries: { run: Run; value: Result | undefined }[];
  camera: string;
  review: (camera: string, run: string) => void;
  selectedRun: string;
  selectRun: (run: string) => void;
}) {
  const official = officialSeedOne(entries);
  const [compareCD, setCompareCD] = useState(false);
  const hasCD = ["C", "D"].every(group=>entries.some(e=>e.run.comparison_group===group));
  const chosen = chooseRun(entries.map(entry => entry.run), clip.sample_id, selectedRun);
  const entry = entries.find(entry => entry.run.id === chosen?.id);
  const run = entry?.run,
    value = entry?.value;
  const sample = run?.release_id === "v2_1" ? "全数据集" : run?.release_id === "v3" ? "10 个样本首片段" : run?.sample || data.experiment?.sample || "sample_01";
  const tasks = new Set(
    data.tasks.filter((t) => (["v2_1", "v3"].includes(run?.release_id || "") || t.sample_id === sample) && (!run?.camera || t.camera_id === run.camera)).map((t) => t.task_id),
  );
  const plannedTasks = new Set(run?.experiment_task_ids || [...tasks]);
  const results = data.results.filter(
    (r) => r.run_id === run?.id && plannedTasks.has(r.task_id),
  );
  const success = new Set(
    results.filter((r) => r.caption_status === "success").map((r) => r.task_id),
  ).size;
  const failed = new Set(
    results.filter((r) => r.caption_status === "failed").map((r) => r.task_id),
  ).size;
  if (data.presentation?.mode === "mentor" || official.length > 0 || run?.release_id === "v2_1") return <CaptionPanel entries={entries} run={run} value={value}
    task={`${clip.clip_id}__${camera}`} camera={camera} review={review} selectRun={selectRun}
    experimentProgress={data.presentation?.mode === "mentor" ? undefined : <p className="experiment-progress" role="status">
      {sample}：{run?.release_id === "v2_1" ? `${run.model_key === "qwen" ? run.official_profile : run.thinking_comparison_role} · ` : run?.release_id === "v3" ? "" : run?.experiment_task_ids ? "本轮五段 " : ""}已生成 {success}／{plannedTasks.size}，失败 {failed}
      {!['v2_1', 'v3'].includes(run?.release_id || '') && run?.experiment_task_ids && <span>；全样本 {tasks.size} 条，剩余任务不在本轮范围</span>}
    </p>}/>;
  if (compareCD && hasCD) return <article className="model-caption"><button onClick={()=>setCompareCD(false)}>返回单组查看</button><CDComparison entries={entries} camera={camera} review={review}/></article>;
  return (
    <article className="model-caption">
      <h2>{run?.model_label || label}</h2>
      {run?.release_id === "v3" ? <p className="experiment-scope">独立窗口 · 无历史 · 多窗口文字汇总</p>
        : run?.display_name && !official.length && <p className="experiment-scope">{run.display_name}</p>}
      {hasCD && <button onClick={()=>setCompareCD(true)}>并排比较 C / D</button>}
      {run?.model_name &&
        !/^[a-f0-9]{32,64}$/.test(run.model_name) &&
        run.model_name !== run.model_label && (
          <p className="actual-model">{run.model_name}</p>
        )}
      {entries.length > 1 && (
        <label>
          实验运行
          <select
            aria-label={`${label} 运行`}
            value={run?.id}
            onChange={(e) => selectRun(e.target.value)}
          >
            {entries.map((e) => (
              <option key={e.run.id} value={e.run.id}>
                {e.run.display_name || `${e.run.comparison_group ? `${e.run.comparison_group} · ` : ""}${e.run.id}`}
              </option>
            ))}
          </select>
        </label>
      )}
      {run ? <p className="experiment-progress" role="status">
        {sample}：{run?.release_id === "v2_1" ? `${run.model_key === "qwen" ? run.official_profile : run.thinking_comparison_role} · ` : run?.release_id === "v3" ? "" : run?.experiment_task_ids ? "本轮五段 " : ""}已生成 {success}／{plannedTasks.size}，失败 {failed}
        {!['v2_1', 'v3'].includes(run?.release_id || '') && run?.experiment_task_ids && <span>；全样本 {tasks.size} 条，剩余任务不在本轮范围</span>}
      </p> : <p className="experiment-progress" role="status">当前样本尚无此模型的结果</p>}
      {run?.release_id === "v3" && !plannedTasks.has(`${clip.clip_id}__${camera}`) && <p className="experiment-scope">本轮只生成各样本的第一个原始子片段；其他片段保留视频和原始标注。</p>}
      {run?.release_id !== "v3" && clip.sample_id !== sample && (
        <p className="experiment-scope">
          当前实验范围是 {sample}；此样本可浏览视频和原始标注。
        </p>
      )}
      {run && <p className="experiment-scope">输入：{run.input_mode === "video" ? "视频序列" : "独立图片"} · {run.sampling_fps ? `${run.model_key === "doubao" && run.input_mode === "video" ? "请求 " : ""}${run.sampling_fps} fps` : "固定帧数"}{run.frame_max_pixels ? ` · 每帧像素预算 ${run.frame_max_pixels}` : ""}</p>}
      <div className="model-output" key={`${camera}/${run?.id}`}>
        <p>
          {value?.caption_status === "success"
            ? value.generated_caption
            : value?.caption_status === "failed"
              ? `生成失败：${value.error || "请重试"}`
              : run?.camera && run.camera !== camera ? "此模型尚未生成该相机结果；请选择 camera2。" : "此片段尚未生成 caption。"}
        </p>
        {hasStructuredContent(value?.annotation) && (
          <details>
            <summary>结构化结果</summary>
            <pre>{JSON.stringify(value?.annotation, null, 2)}</pre>
          </details>
        )}
        {Boolean(value?.windows?.length) && (
          <details>
            <summary>窗口结果与追溯（{value?.windows?.length}）</summary>
            {value?.windows?.map((w) => (
              <section key={w.window_id}>
                <strong>
                  {w.parent_relative_interval_s
                    .map((t) => t.toFixed(2))
                    .join(" — ")}{" "}
                  秒
                </strong>
                <p>{w.generated_caption || w.caption_status}</p>
                {run?.release_id === "v3" && <small>实际采样 {w.sampled_times_s?.length || 0} 帧 · 时间相对此窗口起点</small>}
                <details>
                  <summary>证据与版本</summary>
                  <pre>{JSON.stringify(w, null, 2)}</pre>
                </details>
              </section>
            ))}
          </details>
        )}
        {value?.caption_status === "success" && <details className="caption-details"><summary>资源效率</summary><ResourceMetrics value={value}/><small>{value.provider_sampling_known === false ? "API 请求耗时含传输及服务处理，不等同于本地 GPU 生成耗时。" : "模型生成耗时，不等同于完整任务耗时。"}</small></details>}
        {run?.release_id !== "v3" && <SamplingInput
          run={run?.id}
          task={`${clip.clip_id}__${camera}`}
          result={value?.result_id}
        />}
        {value?.caption_status === "success" && run && (
          <button onClick={() => review(camera, run.id)}>评价此结果</button>
        )}
      </div>
    </article>
  );
}
export function ModelComparison({
  data,
  clip,
  prompt,
  change,
  review,
  modelKey,
  selectModel,
  selectedRun,
  selectRun,
}: {
  data: Data;
  clip: Clip;
  prompt: string;
  change: (p: string) => void;
  review: (camera: string, run: string) => void;
  modelKey: string;
  selectModel: (model: string) => void;
  selectedRun: string;
  selectRun: (run: string) => void;
}) {
  const versions = [
    { key: "v1", id: "baseline-v1", label: "v1 · 纯视觉基线" },
    ...[...new Set(data.runs.map((r) => r.prompt_id))]
      .filter((id) => id !== "baseline-v1")
      .map((id) => ({ key: id === "v3-window-r1" ? "v3" : id === "baseline-v2-1" ? "v2_1" : id === "baseline-v2" ? "v2" : id, id, label: id === "v3-window-r1" ? "v3 · 5 秒窗口试验" : id === "baseline-v2-1" ? "v2.1 · 2 fps 全量" : id === "baseline-v2" ? "v2 · 连续操作" : id })),
  ];
  const [requested, requestedCamera] = normalizeSelection(prompt).split(".");
  const stable = data.presentation?.mode === "mentor";
  const version = stable
    ? versions.find((v) => v.id === data.presentation?.fixed_prompt_id) || versions.find((v) => v.id === "baseline-v2") || versions[0]
    : versions.find((v) => v.key === requested) || versions[0];
  // Current caption experiments use camera2. Historical v1 links can still
  // address their six camera results without adding a misleading selector.
  const camera = stable || ["v2", "v2_1", "v3"].includes(version.key) ? "camera2" : requestedCamera;
  const models = [
    { key: "qwen", label: data.experiment?.model_label || "Qwen" },
    ...data.runs
      .filter((r) => r.prompt_id === version.id && r.model_key !== "qwen")
      .filter(
        (r, i, rows) =>
          rows.findIndex((x) => x.model_key === r.model_key) === i,
      )
      .map((r) => ({ key: r.model_key, label: r.model_label })),
  ];
  const model = models.find((m) => m.key === modelKey) || models[0];
  useEffect(() => { if (model.key !== modelKey) selectModel(model.key); }, [model.key, modelKey, selectModel]);
  useEffect(() => {
    if (requested !== version.key || requestedCamera !== camera) change(`${version.key}.${camera}`);
  }, [requested, requestedCamera, version.key, camera, change]);
  const modelRuns = data.runs.filter(r => r.model_key === model.key && r.prompt_id === version.id)
    .filter(r=>r.release_id !== "v2_1" || !r.experiment_task_ids || r.experiment_task_ids.includes(`${clip.clip_id}__camera2`));
  const preferred = chooseRun(modelRuns, clip.sample_id, selectedRun);
  useEffect(()=>{ if(preferred && preferred.id !== selectedRun) selectRun(preferred.id); },[preferred?.id,selectedRun,selectRun]);
  const available = modelRuns
    .filter((r) => !r.sample || r.sample === clip.sample_id)
    .map((run) => ({
      run,
      value: data.results.find(
        (r) =>
          r.task_id === `${clip.clip_id}__${camera}` && r.run_id === run.id,
      ),
    }));
  const official = officialSeedOne(available);
  const entries = official.length ? official : available;
  const modelControls = <div className="model-choice" role="group" aria-label="模型">
    <span className="control-label">模型</span>
    {models.map(m => {
      const actual = data.runs.find(run => run.model_key === m.key && run.prompt_id === version.id)?.model_name;
      const cloudLabel = m.key === "qwen" ? "Qwen-3.8-27B" : m.key === "doubao" ? actual?.replace(/-lite-\d+$/, "") || m.label : m.label;
      return <button key={m.key} aria-label={`查看 ${m.label} 结果`} aria-pressed={model.key === m.key}
        title={actual && !/^[a-f0-9]{32,64}$/.test(actual) ? actual : m.label}
        onClick={() => selectModel(m.key)}>{cloudLabel}</button>;
    })}
  </div>;
  return (
    <div className="model-workspace caption-view">
      <div className="prompt-choice">
        {!stable && <>
        <label>
          Prompt 版本
          <select
            aria-label="Prompt 版本"
            value={version.key}
            onChange={(e) => change(`${e.target.value}.${["v2","v2_1","v3"].includes(e.target.value) ? "camera2" : camera}`)}
          >
            {versions.map((v) => (
              <option key={v.key} value={v.key}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
        <p>
          {version.key === "v1"
            ? "纯视觉基线：每个原始片段均匀抽取12帧，不使用标注背景或历史，不做窗口汇总。"
            : version.key === "v3" ? "10 个首片段 · 2 fps · 最多 5 秒窗口；窗口独立描述，跨窗口仅做文字汇总，无标注背景或历史。" : version.key === "v2_1" ? "整段视频 · 2 fps · 六部分操作描述；不使用标注背景、历史或窗口。" : version.key === "v2" ? "六部分操作描述或其迭代；不使用标注背景或历史。各运行的采样与输入方式见下方。" : "已导入的实验版本；具体配置以对应运行记录为准。"}
        </p>
        </>}
        {modelControls}
      </div>
      <ModelCaption
        key={`${model.key}/${version.key}`}
        data={data}
        clip={clip}
        label={model.label}
        entries={entries}
        camera={camera}
        review={review}
        selectedRun={preferred?.id || ""}
        selectRun={selectRun}
      />
    </div>
  );
}
