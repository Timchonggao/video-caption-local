"""CLI boundary: immutable configuration and serialized execution."""
import argparse
import json
import math
from pathlib import Path
from caption_system.config import PROJECT, PATHS, VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.store import RunStore, sha
from caption_system.pipeline.context import ordered, predecessors
from caption_system.pipeline.prepare import instructions
from caption_system.results.atomic import atomic_json

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', required=True)
    p.add_argument('--provider', choices=['qwen', 'doubao', 'gemini'], default='qwen')
    p.add_argument('--model')
    p.add_argument('--tasks', default=str(PROJECT / 'metadata/tasks.jsonl'))
    p.add_argument('--camera', choices=[f'camera{i}' for i in range(6)])
    p.add_argument('--sample')
    p.add_argument('--task-id', action='append', help='Repeatable execution filter; preserves predecessor domain')
    p.add_argument('--prompt', help='Complete custom/legacy prompt; default: composed modules')
    p.add_argument('--prompt-id', default='harness-v1')
    p.add_argument('--structured', action='store_true')
    p.add_argument('--contextual', action='store_true')
    p.add_argument('--background', choices=['none', 'sample', 'sample_and_fine_label'], default='none')
    p.add_argument('--context-missing-policy', choices=['continue_without_context', 'wait_for_predecessor'], default='continue_without_context')
    p.add_argument('--window-seconds', type=float)
    p.add_argument('--sampling-fps', type=float)
    p.add_argument('--window-prompt', help='Window evidence module; defaults to original v2 module')
    p.add_argument('--summary-prompt', help='Multi-window summary module; defaults to original v2 module')
    p.add_argument('--frames', type=int, default=8)
    p.add_argument('--max-deviation-s', type=float, default=1.0)
    p.add_argument('--max-pixels', type=int, help='Legacy alias for --frame-max-pixels')
    p.add_argument('--frame-max-pixels', type=int)
    p.add_argument('--input-mode', choices=['images', 'video'], default='images')
    p.add_argument('--video-transport', choices=['files', 'base64', 'auto'], help='Doubao video: Files API by default')
    p.add_argument('--min-frame-tokens', type=int, help='Optional Files preprocessing budget: 16–128')
    p.add_argument('--max-frame-tokens', type=int, help='Optional Files preprocessing budget: 128–640')
    p.add_argument('--max-video-tokens', type=int)
    p.add_argument('--file-processing-timeout', type=float, default=300)
    p.add_argument('--file-poll-interval', type=float, default=2)
    p.add_argument('--file-expire-days', type=int, default=7)
    p.add_argument('--artifact-root',type=Path)
    p.add_argument('--video-cache-root',type=Path)
    p.add_argument('--release-id')
    p.add_argument('--doubao-thinking',choices=['disabled','enabled'],default='disabled')
    p.add_argument('--evidence-run', help='Read frozen frames from a successful prior run')
    p.add_argument('--comparison-group', choices=['A', 'B', 'C', 'D'])
    p.add_argument('--experiment-task-id', action='append', help='Fixed experiment subset, independent of invocation filters')
    p.add_argument('--max-new-tokens', type=int, default=1200)
    p.add_argument('--max-request-bytes', type=int, help='Default: Qwen tensors 512 MiB; API JSON 32 MiB')
    p.add_argument('--limit', type=int)
    p.add_argument('--max-calls', type=int, default=10)
    p.add_argument('--rerun', action='store_true', help='New versions; no automatic cascade')
    p.add_argument('--retry-unknown', action='store_true', help='Acknowledge possibly billed previous submission')
    p.add_argument('--apply', action='store_true')
    p.add_argument('--thinking', action='store_true')
    p.add_argument('--trace-tokens', action='store_true')
    p.add_argument('--caption-max-tokens', type=int)
    p.add_argument('--do-sample',action='store_true')
    p.add_argument('--temperature',type=float)
    p.add_argument('--top-p',type=float)
    p.add_argument('--top-k',type=int)
    p.add_argument('--min-p',type=float)
    p.add_argument('--presence-penalty',type=float)
    p.add_argument('--repetition-penalty',type=float)
    p.add_argument('--base-seed',type=int)
    p.add_argument('--reasoning-effort',choices=['low','medium','xhigh'])
    p.add_argument('--no-preserve-thinking',action='store_true')
    p.add_argument('--official-profile',choices=['off','low','medium','xhigh'])
    p.add_argument('--seed-index',type=int,choices=[1,2])
    p.add_argument('--continue-incomplete',action='store_true')
    p.add_argument('--stop-on-error', action='store_true', help='Stop this invocation after recording any failure')
    a = p.parse_args()
    if (a.video_transport or any(v is not None for v in [a.min_frame_tokens,a.max_frame_tokens,a.max_video_tokens])) and not (a.provider == 'doubao' and a.input_mode == 'video'):
        p.error('File transport and visual token budgets require Doubao video input')
    if a.video_transport == 'base64' and any(v is not None for v in [a.min_frame_tokens,a.max_frame_tokens,a.max_video_tokens]):
        p.error('Visual token budgets require Files API transport')
    sampling = None
    if a.do_sample:
        if a.provider != 'qwen' or a.base_seed is None or a.base_seed < 0:
            p.error('Sampling experiment requires Qwen and an explicit nonnegative base seed')
        required=[a.temperature,a.top_p,a.top_k,a.min_p,a.presence_penalty,a.repetition_penalty]
        if any(x is None for x in required) or any(not math.isfinite(x) for x in required):
            p.error('Explicit finite sampling parameters required')
        if a.temperature<=0 or not 0<a.top_p<=1 or a.top_k<0 or not 0<=a.min_p<=1 or not 0<=a.presence_penalty<=2 or a.repetition_penalty<=0:
            p.error('Invalid sampling parameters')
        sampling={'do_sample':True,'temperature':a.temperature,'top_p':a.top_p,'top_k':a.top_k,'min_p':a.min_p,'presence_penalty':a.presence_penalty,'repetition_penalty':a.repetition_penalty,'base_seed':a.base_seed}
    elif any(x is not None for x in [a.temperature,a.top_p,a.top_k,a.min_p,a.presence_penalty,a.repetition_penalty,a.base_seed]):
        p.error('Sampling parameters require --do-sample')
    if a.reasoning_effort is not None and (a.provider!='qwen' or not a.thinking):
        p.error('Reasoning effort requires enabled Qwen thinking')
    if a.no_preserve_thinking and a.provider != 'qwen':
        p.error('Preserve-thinking control applies to Qwen only')
    if a.official_profile and (not sampling or a.seed_index is None):
        p.error('Official retest requires sampling and seed index')
    if a.official_profile:
        off=a.official_profile=='off'
        expected={'temperature':.7 if off else 1.0,'top_p':.8 if off else .95,'top_k':20,'min_p':0.0,'presence_penalty':1.5 if off else 0.0,'repetition_penalty':1.0}
        if any(sampling[k]!=v for k,v in expected.items()) or a.thinking==off or (not off and a.reasoning_effort!=a.official_profile) or not a.no_preserve_thinking or not a.trace_tokens:
            p.error('Official profile parameters do not match the configured recipe')
    if (a.thinking or a.trace_tokens or a.caption_max_tokens) and a.provider != 'qwen':
        p.error('Thinking/token trace experiment applies to Qwen only')
    if a.thinking and not a.trace_tokens:
        p.error('Thinking requires token trace for completeness validation')
    if a.caption_max_tokens is not None and (a.caption_max_tokens < 1 or not a.trace_tokens):
        p.error('Caption budget requires tracing and positive limit')
    if a.max_pixels is not None and a.frame_max_pixels is not None and a.max_pixels != a.frame_max_pixels:
        p.error('Conflicting --max-pixels and --frame-max-pixels')
    a.max_pixels = a.frame_max_pixels if a.frame_max_pixels is not None else (a.max_pixels if a.max_pixels is not None else 2080000)
    if a.input_mode == 'video' and (a.provider not in ['qwen', 'doubao'] or not a.sampling_fps or a.window_seconds is not None):
        p.error('Video requires Qwen/Doubao and positive sampling FPS, without windows')
    if a.provider == 'doubao' and a.input_mode == 'video' and not 0.2 <= a.sampling_fps <= 5:
        p.error('Ark video FPS must be within 0.2–5')
    if a.evidence_run and (a.provider != 'qwen' or a.window_seconds is not None):
        p.error('Frozen evidence experiments require Qwen without windows')
    if a.window_seconds is not None and (a.provider != 'qwen' or not 0 < a.window_seconds <= 5 or not a.sampling_fps or a.sampling_fps <= 0):
        p.error('Window v2 requires Qwen, 0 < window seconds <= 5 and positive sampling FPS')
    if (a.window_prompt or a.summary_prompt) and a.window_seconds is None:
        p.error('Window/summary prompt overrides require window mode')
    if a.sampling_fps is not None and a.sampling_fps <= 0:
        p.error('Sampling FPS must be positive')
    if a.max_request_bytes is None:
        a.max_request_bytes = (512 if a.provider == 'qwen' else 32) * 1024 * 1024
    if min(a.frames, a.max_pixels, a.max_new_tokens, a.max_calls, a.max_request_bytes) < 1 or a.max_deviation_s < 0 or a.limit is not None and a.limit < 1:
        p.error('Invalid budgets')
    if a.doubao_thinking=='enabled' and not (a.provider=='doubao' and a.input_mode=='video'):p.error('Doubao thinking requires video provider')
    if a.provider == 'doubao' and a.input_mode == 'video' and (not a.prompt or a.structured or a.contextual or a.background != 'none'):
        p.error('Ark video experiment requires plaintext custom prompt without context/background')
    if a.provider != 'qwen' and not a.model:
        p.error('Specify provider model ID')
    domain = ordered([t for t in read_jsonl(a.tasks) if (not a.camera or t['camera_id'] == a.camera) and (not a.sample or t['sample_id'] == a.sample)])
    selected = [t for t in domain if not a.task_id or t['task_id'] in a.task_id]
    if a.task_id and set(a.task_id) - {t['task_id'] for t in domain}:
        raise ValueError('Selection contains unknown/out-of-domain task IDs')
    if a.experiment_task_id:
        experiment_ids = set(a.experiment_task_id)
        if experiment_ids - {t['task_id'] for t in domain}:
            raise ValueError('Experiment contains out-of-domain tasks')
        if a.task_id and set(a.task_id) - experiment_ids:
            raise ValueError('Invocation outside experiment scope')
        selected = [t for t in selected if t['task_id'] in experiment_ids]
    if not selected:
        raise ValueError('No tasks matched')
    prompt, modules = instructions(a.prompt)
    model = a.model or PATHS['model_path']
    source = PROJECT / 'src/caption_system'
    config = {'schema_version': 'harness-v1', 'version': VERSION, 'provider': a.provider,
              'model_name': Path(model).name if a.provider == 'qwen' else model, 'model_path': model,
              'model_key': a.provider, 'model_label': json.loads((PROJECT / 'configs/models.json').read_text())[a.provider]['label'],
              'prompt_id': a.prompt_id, 'prompt_modules': modules, 'task_manifest_sha256': sha(a.tasks),
              'sample': a.sample, 'camera': a.camera, 'frames': a.frames, 'max_pixels': a.max_pixels,
              'frame_max_pixels': a.max_pixels, 'input_mode': a.input_mode,
              'max_new_tokens': a.max_new_tokens, 'max_request_bytes': a.max_request_bytes,
              'max_deviation_s': a.max_deviation_s, 'structured': not a.prompt or a.structured,
              'contextual': a.contextual, 'background': a.background, 'context_missing_policy': a.context_missing_policy,
              'code_sha256': {str(f.relative_to(source)): sha(f) for f in sorted(source.rglob('*.py'))},
              'decode_concurrency': 1, 'request_concurrency': 1, 'prepared_queue_limit': 1}
    if a.artifact_root:config['artifact_root']=str(a.artifact_root.resolve())
    if a.release_id:config['release_id']=a.release_id
    if sampling:
        config.update(sampling=sampling,reasoning_effort=a.reasoning_effort,preserve_thinking=False if a.no_preserve_thinking else None)
    if a.official_profile:
        config.update(experiment_family='official-qwen38-v2',official_profile=a.official_profile,seed_index=a.seed_index)
    if a.thinking or a.trace_tokens:
        config.update(thinking=a.thinking,trace_tokens=a.trace_tokens,caption_max_tokens=a.caption_max_tokens,thinking_comparison_role='on' if a.thinking else 'off')
    if a.comparison_group:
        config['comparison_group'] = a.comparison_group
    if a.experiment_task_id:
        config['experiment_task_ids'] = sorted(set(a.experiment_task_id))
    if a.evidence_run:
        from caption_system.data.evidence import evidence_index
        config['evidence_run'] = a.evidence_run
        config['evidence_input_ids'] = evidence_index(PROJECT / 'runs', a.evidence_run,
                config.get('experiment_task_ids') or [t['task_id'] for t in domain])
    if a.sampling_fps is not None:
        config['sampling_fps'] = a.sampling_fps
    if a.window_seconds is not None:
        config.update(schema_version='window-v2', window_seconds=a.window_seconds, sampling_fps=a.sampling_fps, background='sample_and_fine_label', contextual=True, context_missing_policy='wait_for_predecessor')
        config['window_prompt'] = Path(a.window_prompt or PROJECT / 'prompts/modules/05_window_v2.txt').read_text()
        config['summary_prompt'] = Path(a.summary_prompt or PROJECT / 'prompts/modules/06_summary_v2.txt').read_text()
    if a.provider == 'qwen':
        config['model_config_sha256'] = sha(Path(model) / 'config.json')
        config['processor_sha256'] = {f.name: sha(f) for f in Path(model).glob('*.json')}
        from caption_system.models.qwen import Qwen
        backend = Qwen(model, a.max_pixels, a.max_new_tokens, a.input_mode, a.sampling_fps, a.thinking, a.trace_tokens, a.caption_max_tokens, sampling, a.reasoning_effort, False if a.no_preserve_thinking else None)
    else:
        if a.provider == 'doubao' and a.input_mode == 'video':
            from caption_system.models.doubao_video import DoubaoVideo
            backend = DoubaoVideo(model,a.max_new_tokens,a.sampling_fps,transport=a.video_transport or 'files',
                min_frame_tokens=a.min_frame_tokens,max_frame_tokens=a.max_frame_tokens,max_video_tokens=a.max_video_tokens,
                file_processing_timeout=a.file_processing_timeout,file_poll_interval=a.file_poll_interval,
                file_expire_days=a.file_expire_days,retry_unknown=a.retry_unknown,thinking=a.doubao_thinking,video_cache_root=a.video_cache_root)
            # Video sampling and visual processing are provider-managed. These
            # image-mode defaults never reach Ark and must not describe this run.
            config.pop('frames', None)
            config.pop('max_pixels', None)
            config.update(frame_max_pixels=None,visual_processing='provider_managed',thinking=a.doubao_thinking,
                thinking_comparison_role='on' if a.doubao_thinking=='enabled' else 'off',
                transport={'files':'files_api_chat','base64':'base64_mp4_chat','auto':'auto_video_chat'}[backend.transport])
            if a.video_cache_root:config['video_cache_root']=str(a.video_cache_root.resolve())
            if backend.transport in ('files','auto'):
                config.update(file_preprocess_configs=backend.preprocess,file_processing_timeout=a.file_processing_timeout,
                              file_poll_interval=a.file_poll_interval,file_expire_days=a.file_expire_days)
        else:
            from caption_system.models.api import Api
            backend = Api(a.provider, model, a.max_pixels, a.max_new_tokens)
        backend.max_request_bytes = a.max_request_bytes
    from caption_system.pipeline.execute import execute
    store = RunStore(a.run, config, domain)
    try:
        store.event('invocation', selected_task_ids=[t['task_id'] for t in selected], apply=a.apply,
                    rerun=a.rerun, max_calls=a.max_calls, limit=a.limit)
        if a.window_seconds is not None:
            from caption_system.pipeline.windows import execute_windows
            execute_windows(store, selected, config, backend, prompt, a)
        else:
            execute(store, selected, predecessors(domain), config, backend, prompt, a)
        runtime_path = store.root / 'runtime.json'
        runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
        runtime.update(backend.runtime)
        atomic_json(runtime_path, runtime)
    finally:
        store.close()

if __name__ == '__main__':
    main()
