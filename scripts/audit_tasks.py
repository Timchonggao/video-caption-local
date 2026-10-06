"""Verify original annotation intervals and camera tasks without model inference."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from caption_system.config import PROJECT
from caption_system.data.tasks import read_jsonl
from caption_system.video.sampling import sample_task
clips = read_jsonl(PROJECT / 'metadata/clips.jsonl')
tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
errors = []
for clip in clips:
    annotations = json.loads((PROJECT / 'metadata/annotations' / f'{clip['sample_id']}.json').read_text())
    original = annotations[0]['segments_info'][clip['segment_index'] - 1]['sub_segments_info'][clip['subtask_index'] - 1]
    for key, target in [('start_time_s', 'clip_start_time_s'), ('end_time_s', 'clip_end_time_s')]:
        if original.get(key, 0) != clip[target]:
            errors.append(clip['clip_id'])
    for task in [t for t in tasks if t['clip_id'] == clip['clip_id']]:
        if not Path(task['media_path']).is_file():
            errors.append(task['task_id'])
checks = []
for sid in sorted({t['sample_id'] for t in tasks}):
    for camera in [f'camera{i}' for i in range(6)]:
        group = [t for t in tasks if t['sample_id'] == sid and t['camera_id'] == camera]
        for task in [group[0], group[-1]]:
            try:
                frames, times, _, duration = sample_task(task, 2)
                if not frames or any((t < 0 or t >= duration for t in times)):
                    raise ValueError('Frame outside original interval')
                checks.append({'task_id': task['task_id'], 'sampled_times_s': times, 'duration_s': duration})
            except Exception as e:
                errors.append({'task_id': task['task_id'], 'error': str(e)})
report = {'clips': len(clips), 'tasks': len(tasks), 'false_tasks_included': sum((not t['original_is_success'] for t in tasks)), 'sampling_checks': checks, 'errors': errors, 'status': 'pass' if not errors else 'failed'}
(PROJECT / 'reports/data-checks').mkdir(parents=True, exist_ok=True)
(PROJECT / 'reports/data-checks/task-audit.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'], len(checks), 'sampling checks')
if errors:
    raise SystemExit(1)
