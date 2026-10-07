import type { Data, Run } from "./types";

export function chooseRun(runs: Run[], sample: string, preferredId: string): Run | undefined {
  const candidates = runs.filter(run => !run.sample || run.sample === sample);
  const preferred = runs.find(run => run.id === preferredId);
  return candidates.find(run => run.id === preferredId)
    || (preferred?.official_profile ? candidates.find(run =>
      run.official_profile === preferred.official_profile && run.seed_index === preferred.seed_index) : undefined)
    || candidates.find(run => run.official_profile === "off" && run.seed_index === 1)
    || candidates.find(run => run.thinking_comparison_role === "off")
    || candidates.find(run => run.comparison_group === "C")
    || candidates.at(-1);
}

export function availableClipIds(data: Data, model: string, prompt: string, camera: string, preferredId: string): Set<string> {
  let runs = data.runs.filter(run => run.model_key === model && run.prompt_id === prompt);
  const official = runs.filter(run => run.experiment_family === "official-qwen38-v2" && run.seed_index === 1);
  if (official.length) runs = official;
  const selected = new Map(data.clips.map(clip => {
    const scope=runs.filter(run=>run.release_id !== "v2_1" || !run.experiment_task_ids || run.experiment_task_ids.includes(`${clip.clip_id}__camera2`));
    return [clip.clip_id,chooseRun(scope,clip.sample_id,preferredId)?.id];
  }));
  return new Set(data.results.filter(result => result.caption_status === "success"
    && result.camera_id === camera && result.run_id === selected.get(result.clip_id))
    .map(result => result.clip_id));
}
