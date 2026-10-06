import type { Result } from "../types";
const seconds = (value?: number | null) => value == null ? "未记录" : `${value.toFixed(2)} 秒`;
export function ResourceMetrics({ value }: {value?: Result}) {
  const memory = value?.peak_gpu_allocated_bytes;
  return <dl className="resource-metrics" aria-label="资源效率">
    <dt>{value?.provider_sampling_known === false ? "API 请求（含传输）" : "模型生成"}</dt><dd>{seconds(value?.generation_seconds)}</dd>
    <dt>输入 / 输出 token</dt><dd>{value?.input_tokens ?? "未记录"} / {value?.generated_tokens ?? "未记录"}</dd>
    {value?.thinking_tokens != null && <>
      <dt>思考 / 最终 caption token</dt><dd>{value.thinking_tokens} / {value.caption_tokens}</dd>
      <dt>首 token 延迟</dt><dd>{seconds(value.first_token_seconds)}</dd>
      <dt>思考阶段（含预填充）</dt><dd>{seconds(value.thinking_seconds)}</dd>
      <dt>思考解码（首 token 后）</dt><dd>{seconds(value.thinking_decode_seconds)}</dd>
      <dt>最终 caption 阶段</dt><dd>{seconds(value.caption_seconds)}</dd>
      <dt>输出完整性</dt><dd>思考：{value.thinking_complete ? "完整" : "未结束"}；caption：{value.caption_complete ? "完整" : "未完成"}</dd>
    </>}
    {value?.effective_sampling && <>
      <dt>实际采样参数</dt><dd>T {value.effective_sampling.temperature} · p {value.effective_sampling.top_p} · k {value.effective_sampling.top_k} · presence {value.effective_sampling.presence_penalty}</dd>
      <dt>任务随机种子</dt><dd>{value.task_seed || "未记录"}</dd>
      <dt>effort</dt><dd>{value.reasoning_effort || "关闭思考"}</dd>
    </>}
    <dt>峰值分配显存</dt><dd>{memory ? Object.entries(memory).map(([gpu, bytes]) => `GPU${gpu} ${(bytes / 2 ** 30).toFixed(2)} GiB`).join("；") : value?.provider_sampling_known === false ? "服务端不可见" : "未记录"}</dd>
    <dt>实际画面尺寸</dt><dd>{value?.provider_processed_dimensions_known === false ? `服务端未返回；上传源片段 ${value.source_video_dimensions?.join("×") || "未记录"}` : value?.processed_sizes?.[0]?.join("×") || "未记录"}</dd>
  </dl>;
}
