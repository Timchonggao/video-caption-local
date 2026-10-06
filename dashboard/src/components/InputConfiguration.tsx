import type { Run } from "../types";

export function InputConfiguration({ run }: {run?: Run}) {
  if (!run) return null;
  const providerVideo = run.model_key === "doubao" && run.input_mode === "video";
  return <p className="input-configuration">输入：{run.input_mode === "video" ? "视频序列" : "独立图片"}
    {run.sampling_fps ? ` · ${providerVideo ? "请求 " : ""}${run.sampling_fps} fps` : " · 固定帧数"}
    {run.frame_max_pixels && !providerVideo ? ` · 每帧像素预算 ${run.frame_max_pixels}` : ""}
  </p>;
}
