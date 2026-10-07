export type Clip = {
  clip_id: string;
  sample_id: string;
  domain: string;
  scenario: string;
  bold_mark: string;
  subtask_label: string;
  segment_label: string;
  clip_start_time_s: number;
  clip_end_time_s: number;
  clip_duration_s: number;
};
export type Task = {
  task_id: string;
  clip_id: string;
  sample_id: string;
  camera_id: string;
  media_id: string;
};
export type Media = {
  id: string;
  kind: string;
  camera: string;
  width: number;
  height: number;
  first_available_time_s: number;
  last_available_time_s: number;
  source_to_video_offset_s: number;
};
export type Inventory = { sample_id: string; media: Media[] };
export type Run = {
  release_id?: string;
  experiment_family?: string;
  official_profile?: string | null;
  seed_index?: number | null;
  reasoning_effort?: string | null;
  sampling?: Record<string,number|boolean> | null;
  thinking?: boolean;
  thinking_comparison_role?: "off" | "on" | null;
  display_name?: string;
  input_mode?: "images" | "video";
  frame_max_pixels?: number;
  experiment_task_ids?: string[] | null;
  comparison_group?: string | null;
  camera?: string | null;
  sampling_fps?: number | null;
  sample?: string | null;
  id: string;
  model_key: string;
  model_label: string;
  model_name: string;
  prompt_id: string;
};
export type Result = {
  provider_transport?: "base64" | "files";
  estimated_cost_cny?: number | null;
  caption_tokens_note?: string;
  effective_sampling?: {do_sample:boolean;temperature:number;top_p:number;top_k:number;min_p:number;presence_penalty:number;repetition_penalty:number;base_seed:number};
  task_seed?: string;
  reasoning_effort?: string | null;
  thinking_enabled?: boolean;
  thinking_tokens?: number | null;
  caption_tokens?: number | null;
  thinking_seconds?: number | null;
  thinking_decode_seconds?: number | null;
  caption_seconds?: number | null;
  first_token_seconds?: number | null;
  thinking_complete?: boolean | null;
  caption_complete?: boolean | null;
  provider_sampling_known?: boolean;
  provider_processed_dimensions_known?: boolean;
  source_video_dimensions?: number[];
  generation_seconds?: number | null;
  input_tokens?: number | null;
  generated_tokens?: number | null;
  peak_gpu_allocated_bytes?: Record<string, number> | null;
  processed_sizes?: number[][] | null;
  result_id?: string;
  task_id: string;
  clip_id: string;
  camera_id: string;
  run_id: string;
  caption_status: string;
  generated_caption: string;
  error?: string;
  annotation?: unknown;
  windows?: {
    window_id: string;
    source_interval_s: number[];
    parent_relative_interval_s: number[];
    caption_status: string;
    generated_caption: string;
    result_id?: string;
    previous_result_id?: string;
    sampled_times_s: number[];
    annotation?: unknown;
  }[];
};
export type Review = {
  result_id?: string;
  task_id: string;
  camera_id: string;
  clip_id: string;
  target: string;
  run_id: string;
  count: number;
};
export type SamplingEvidence = {
  source_evidence_available?: boolean;
  provider_sampling_known?: boolean;
  requested_fps?: number;
  video_export?: {source_dimensions:number[];source_frame_count:number;audio:boolean;bytes:number};
  input_mode?: "images" | "video";
  source_evidence?: {run_id?: string; input_id?: string};
  temporal_evidence?: {real_frame_count: number; encoded_frame_count: number; padding_count: number; groups: {frame_indices: number[]; timestamp_s: number; display_timestamp_s: number}[]};
  display_profile?: string;
  status: "missing" | "prepared" | "result";
  message?: string;
  input_id?: string;
  result_id?: string;
  frames: {
    url: string;
    relative_time_s: number;
    source_time_s: number;
    requested_relative_time_s: number;
    deviation_s: number;
    processed_size?: number[] | null;
    duplicate_of?: number | null;
  }[];
};
export type Data = {
  presentation?: {
    mode: "mentor";
    fixed_prompt_id: string;
  } | null;
  review_features?: string[];
  experiment?: {
    sample: string;
    run_id: string;
    prompt_id: string;
    model_label: string;
    frames: number;
  };
  version: string;
  clips: Clip[];
  tasks: Task[];
  runs: Run[];
  results: Result[];
  reviews: Review[];
};
export const time = (n: number) =>
  `${Math.floor(n / 60)}:${(n % 60).toFixed(2).padStart(5, "0")}`;
export const domainLabels: Record<string, string> = {
  domestic_services: "家庭服务",
  business: "商业场景",
  industry: "工业场景",
};
