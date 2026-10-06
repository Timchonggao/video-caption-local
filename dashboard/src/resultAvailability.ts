import type { Data, Run } from "./types";

export function chooseRun(runs: Run[], sample: string, preferredId: string): Run | undefined {
  const candidates = runs.filter(run => !run.sample || run.sample === sample);
  const preferred = runs.find(run => run.id === preferredId);
  return candidates.find(run => run.id === preferredId)
    || (preferred?.official_profile ? candidates.find(run =>
      run.official_profile === preferred.official_profile && run.seed_index === preferred.seed_index) : undefined)
    || candidates.find(run => run.official_profile === "off" && run.seed_index === 1)
    || candidates.find(run => run.comparison_group === "C")
    || candidates.at(-1);
}

export function availableClipIds(data: Data, model: string, prompt: string, camera: string, preferredId: string): Set<string> {
  let runs = data.runs.filter(run => run.model_key === model && run.prompt_id === prompt);
  const official = runs.filter(run => run.experiment_family === "official-qwen38-v2" && run.seed_index === 1);
  if (official.length) runs = official;
  const samples = new Map(data.clips.map(clip => [clip.clip_id, clip.sample_id]));
  const selected = new Map([...new Set(samples.values())].map(sample => [sample, chooseRun(runs, sample, preferredId)?.id]));
  return new Set(data.results.filter(result => result.caption_status === "success"
    && result.camera_id === camera && result.run_id === selected.get(samples.get(result.clip_id) || ""))
    .map(result => result.clip_id));
}
