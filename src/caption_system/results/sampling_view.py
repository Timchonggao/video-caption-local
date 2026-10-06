"""Read persisted sampling evidence; never generate frames or expose disk paths."""
import json
import re
from pathlib import Path
from urllib.parse import urlencode
from caption_system.results.store import sha


def _safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid evidence identity')
    return value


def _run(root, run):
    root = Path(root).resolve()
    directory = root / _safe_id(run)
    if not directory.resolve().is_relative_to(root) or not (directory / 'config.json').is_file():
        raise FileNotFoundError('Run not found')
    return directory


def _bundle(directory, input_id, task):
    path = directory / 'inputs' / (_safe_id(input_id) + '.json')
    if not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError('Invalid input path')
    bundle = json.loads(path.read_text())
    if bundle.get('task_id') != task or bundle.get('input_id') != input_id:
        raise ValueError('Input task mismatch')
    return bundle


def sampling_evidence(root, run, task, result=None):
    directory = _run(root, run)
    _safe_id(task)
    record = None
    if result:
        path = directory / 'versions' / (_safe_id(result) + '.json')
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Invalid result path')
        record = json.loads(path.read_text())
        if record.get('task_id') != task:
            raise ValueError('Result task mismatch')
    else:
        active = directory / 'active.json'
        if active.is_file():
            index = json.loads(active.read_text())
            selected = index.get('selection', index).get(task)
            if selected:
                path = directory / 'versions' / (_safe_id(selected) + '.json')
                if not path.resolve().is_relative_to(directory.resolve()):
                    raise ValueError('Invalid result path')
                record = json.loads(path.read_text())
                if record.get('task_id') != task:
                    raise ValueError('Result task mismatch')
    input_id = record.get('input_id') if record else None
    if not input_id and not record:
        preview = directory / 'preview.json'
        if preview.is_file():
            entries = json.loads(preview.read_text()).get('inputs', [])
            input_id = next((x.get('input_id') for x in entries if x.get('task_id') == task), None)
    if not input_id:
        return {'status': 'missing', 'frames': [], 'message': '此任务尚无保存的采样输入'}
    bundle = _bundle(directory, input_id, task)
    sizes = bundle.get('request', {}).get('image_sizes', [])
    frames = []
    for i, item in enumerate(bundle.get('frames', [])):
        frames.append({**{key: item.get(key) for key in (
            'requested_relative_time_s', 'relative_time_s', 'source_time_s',
            'deviation_s', 'pts', 'time_base', 'duplicate_of', 'size')},
            'processed_size': sizes[i] if i < len(sizes) else None,
            'url': '/api/sampling/frame?' + urlencode({'run': run, 'task': task, 'input': input_id, 'frame': i})})
    return {'status': 'result' if record else 'prepared', 'run_id': run, 'task_id': task,
            'input_id': input_id, 'result_id': record.get('result_id') if record else None,
            'ready': bundle.get('ready', False), 'source_interval_s': bundle.get('source_interval_s'),
            'input_mode': bundle.get('input_mode', 'images'),
            'source_evidence': {k: v for k, v in bundle.get('source_evidence', {}).items() if k in ('run_id', 'input_id')},
            'source_evidence_available': bool(bundle.get('source_evidence', {}).get('run_id') and (Path(root) / _safe_id(bundle['source_evidence']['run_id']) / 'config.json').is_file()),
            'temporal_evidence': bundle.get('request', {}).get('temporal_evidence'),
            'encoded_timestamps_s': bundle.get('request', {}).get('encoded_timestamps_s'),
            'provider_sampling_known': bundle.get('request', {}).get('provider_sampling_known'),
            'requested_fps': bundle.get('request', {}).get('requested_fps'),
            **({'provider_transport': 'files', 'requested_preprocessing': bundle['request']['file_preprocess_configs']}
               if bundle.get('request', {}).get('transport') == 'files' else {}),
            'video_export': {k:v for k,v in bundle.get('request', {}).get('video_export', {}).items() if k in ('source_dimensions','source_frame_count','audio','source_interval_s','bytes')},
            'frames': frames}


def sampling_frame(root, run, task, input_id, index):
    directory = _run(root, run)
    bundle = _bundle(directory, input_id, _safe_id(task))
    if not 0 <= index < len(bundle.get('frames', [])):
        raise ValueError('Invalid frame index')
    frame = bundle['frames'][index]
    relative = Path(frame['path'])
    path = (directory / relative).resolve()
    if relative.is_absolute() or not relative.parts or relative.parts[0] != 'artifacts' or not path.is_relative_to(directory.resolve()) or path.suffix != '.png':
        raise ValueError('Invalid frame path')
    if sha(path) != frame['sha256']:
        raise ValueError('Saved frame changed')
    return path
