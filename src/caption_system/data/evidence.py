"""Read a frozen prior input without decoding or changing the source run."""
import json
import re
from pathlib import Path
from PIL import Image
from caption_system.results.store import sha


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Invalid evidence identity')
    return value


def evidence_index(root, run, task_ids):
    directory = Path(root) / safe_id(run)
    active = json.loads((directory / 'active.json').read_text())
    selected = active.get('selection', active)
    result = {}
    for task in task_ids:
        record = json.loads((directory / 'versions' / (safe_id(selected[task]) + '.json')).read_text())
        if record['task_id'] != task or record['caption_status'] != 'success':
            raise ValueError('Source evidence requires matching successful result')
        result[task] = safe_id(record['input_id'])
    return result


def read_evidence(root, run, input_id, task, max_deviation_s):
    directory = (Path(root) / safe_id(run)).resolve()
    bundle = json.loads((directory / 'inputs' / (safe_id(input_id) + '.json')).read_text())
    interval = [task['clip_start_time_s'], task['clip_end_time_s']]
    if bundle['task_id'] != task['task_id'] or bundle['source_interval_s'] != interval or not bundle['ready']:
        raise ValueError('Source evidence identity/interval mismatch')
    if bundle['video_sha256'] != sha(task['media_path']):
        raise ValueError('Source media changed')
    frames, metadata = [], []
    for detail in bundle['frames']:
        from caption_system.results.artifacts import resolve_artifact
        relative = Path(detail['path'])
        path = resolve_artifact(directory, relative) if relative.parts and relative.parts[0] == 'artifacts' else (directory / relative).resolve()
        if (relative.is_absolute() or (relative.parts[0] != 'artifacts' and not path.is_relative_to(directory))
                or path.suffix != '.png' or sha(path) != detail['sha256']):
            raise ValueError('Source evidence image changed or path invalid')
        if not interval[0] <= detail['source_time_s'] < interval[1] or abs(detail['deviation_s']) > max_deviation_s:
            raise ValueError('Invalid source frame time')
        if metadata and detail['source_time_s'] <= metadata[-1]['source_time_s']:
            raise ValueError('Source frames must have unique increasing PTS')
        with Image.open(path) as image:
            frames.append(image.convert('RGB').copy())
        metadata.append(dict(detail))
    if not frames:
        raise ValueError('Source evidence is empty')
    return frames, metadata, bundle
