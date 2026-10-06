"""One stable task per original subsegment and camera, without validity filtering."""
import json
from pathlib import Path
from caption_system.config import PROJECT, PATHS

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def task_id(clip_id, camera_id):
    if camera_id not in [f'camera{i}' for i in range(6)]:
        raise ValueError('Unknown camera')
    return f'{clip_id}__{camera_id}'

def build_tasks(clips, inventories):
    lookup = {r['sample_id']: r for r in inventories}
    tasks = []
    for clip in clips:
        cameras = sorted((m for m in lookup[clip['sample_id']]['media'] if m['kind'] == 'video'), key=lambda m: int(m['camera'][6:]))
        if [m['camera'] for m in cameras] != [f'camera{i}' for i in range(6)]:
            raise ValueError('Expected all six cameras')
        if clip['clip_end_time_s'] <= clip['clip_start_time_s']:
            raise ValueError('Invalid original interval')
        for media in cameras:
            tasks.append({**{k: v for k, v in clip.items() if k not in ['mcap_path', 'media_path', 'default_media_id', 'video_timestamp_offset_s']}, 'task_id': task_id(clip['clip_id'], media['camera']), 'camera_id': media['camera'], 'media_id': media['id'], 'media_path': str(Path(PATHS['media_root']) / clip['sample_id'] / media['file']), 'video_timestamp_offset_s': media.get('source_to_video_offset_s', 0), 'first_available_time_s': media['first_available_time_s'], 'last_available_time_s': media['last_available_time_s']})
    if len({t['task_id'] for t in tasks}) != len(tasks):
        raise ValueError('Duplicate task')
    return tasks

def main():
    tasks = build_tasks(read_jsonl(PROJECT / 'metadata/clips.jsonl'), json.loads((PROJECT / 'metadata/samples.json').read_text()))
    (PROJECT / 'metadata/tasks.jsonl').write_text(''.join((json.dumps(t, ensure_ascii=False) + '\n' for t in tasks)))
    print(f'{len(tasks)} tasks; no is_success or validity filtering')
if __name__ == '__main__':
    main()
