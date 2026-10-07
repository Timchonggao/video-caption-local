"""Load server runs without exposing machine paths to the browser."""
import json
from caption_system.config import PROJECT, VERSION
from caption_system.results.store import validate_result
from caption_system.data.tasks import read_jsonl

def load_runs(tasks, root=None):
    runs = []
    results = []
    lookup = {r['task_id']: r for r in tasks}
    visibility = PROJECT / 'configs/dashboard.json'
    hidden = set(json.loads(visibility.read_text()).get('hidden_runs', [])) if visibility.exists() else set()
    for path in sorted((root or PROJECT / 'runs').glob('*/config.json')):
        if path.parent.name in hidden:
            continue
        config = json.loads(path.read_text())
        if config.get('version') != VERSION:
            continue
        runs.append({'id': path.parent.name, 'model_key': config['model_key'], 'model_name': config['model_name'], 'model_label': config['model_label'], 'prompt_id': config['prompt_id'], 'sample': config.get('sample'), 'camera': config.get('camera'), 'sampling_fps': config.get('sampling_fps'), 'input_mode': config.get('input_mode', 'images'), 'frame_max_pixels': config.get('frame_max_pixels', config.get('max_pixels')), 'experiment_task_ids': config.get('experiment_task_ids'), 'comparison_group': config.get('comparison_group'), 'thinking_comparison_role': config.get('thinking_comparison_role'), 'thinking': config.get('thinking', False) if config.get('provider') == 'qwen' else config.get('thinking') == 'enabled', 'release_id': config.get('release_id'), 'experiment_family': config.get('experiment_family', 'legacy-greedy'), 'official_profile':config.get('official_profile'), 'seed_index':config.get('seed_index'), 'sampling':config.get('sampling'), 'reasoning_effort':config.get('reasoning_effort')})
        rp = path.parent / 'results.jsonl'
        active = path.parent / 'active.json'
        if active.exists():
            index = json.loads(active.read_text())
            rows = [json.loads((path.parent / 'versions' / (rid + '.json')).read_text()) for rid in index.get('selection', index).values()]
            for r in rows:
                r.update(index.get('flags', {}).get(r['result_id'], {}))
        else:
            rows = read_jsonl(rp) if rp.exists() else []
        seen = set()
        for r in rows:
            validate_result(r, lookup)
            if r['task_id'] in seen:
                raise ValueError('Duplicate result task')
            seen.add(r['task_id'])
            results.append({**{k: r.get(k) for k in ['task_id', 'clip_id', 'camera_id', 'caption_status', 'generated_caption', 'error', 'annotation', 'result_id', 'context_changed', 'output_status', 'execution_status', 'windows', 'summary_method', 'quality_status', 'generation_seconds', 'input_tokens', 'generated_tokens', 'peak_gpu_allocated_bytes', 'processed_sizes', 'requested_fps', 'provider_sampling_known', 'provider_processed_dimensions_known', 'source_video_dimensions', 'thinking_enabled', 'thinking_tokens', 'caption_tokens', 'delimiter_tokens', 'terminal_tokens', 'thinking_complete', 'caption_complete', 'first_token_seconds', 'thinking_seconds', 'thinking_decode_seconds', 'caption_seconds', 'timing_note', 'effective_sampling', 'task_seed', 'reasoning_effort','provider_transport','estimated_cost_cny','caption_tokens_note']}, 'run_id': path.parent.name})
    for result in results:
        if result.get('task_seed') is not None:
            result['task_seed'] = str(result['task_seed'])
    comparison_path = PROJECT / 'configs/video_input_comparison.json'
    if comparison_path.exists():
        comparison = json.loads(comparison_path.read_text())
        for run in runs:
            for group, spec in comparison['groups'].items():
                if run['id'] == spec['run_id']:
                    run['experiment_task_ids'] = comparison['task_ids']
                    run['comparison_group'] = None if comparison.get('retired') else group
                    if comparison.get('retired'):
                        run['display_name'] = '视频＋r3 · v2 基线'
    for run in runs:
        if run.get('experiment_family') == 'official-qwen38-v2':
            mode = '关闭思考' if run['official_profile']=='off' else run['official_profile']
            run['display_name'] = f'官方采样 · {mode}'
        elif run.get('thinking_comparison_role'):
            run['display_name'] = '视频＋r3 · thinking ' + ('开启' if run['thinking'] else '关闭（计时对照）')
    return (runs, results)
