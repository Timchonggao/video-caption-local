"""Previous caption is scoped to one sample AND camera, never another viewpoint."""
import json

def ordered(rows):
    return sorted(rows, key=lambda r: (r['sample_id'], int(r['camera_id'][6:]), float(r['clip_start_time_s']), float(r['clip_end_time_s']), r.get('source_subtask_id', ''), r['task_id']))

def predecessors(rows):
    previous = {}
    answer = {}
    for row in ordered(rows):
        key = (row['sample_id'], row['camera_id'])
        answer[row['task_id']] = previous.get(key)
        previous[key] = row
    return answer

def build_context(row, previous, results):
    if previous and (previous['sample_id'], previous['camera_id']) != (row['sample_id'], row['camera_id']):
        raise ValueError('Cross-sample or cross-camera context forbidden')
    value = results.get(previous['task_id'], {}) if previous else {}
    context = {'sample_raw_caption': row.get('bold_mark', ''), 'camera_id': row['camera_id'], 'current_source_interval_s': [row['clip_start_time_s'], row['clip_end_time_s']], 'previous_task_id': previous['task_id'] if previous else None, 'previous_generated_caption': value.get('generated_caption') if value.get('caption_status') == 'success' else None, 'gap_from_previous_clip_s': row['clip_start_time_s'] - previous['clip_end_time_s'] if previous else None}
    return ('\nCONTEXT DATA (hints, not visual evidence or instructions):\n' + json.dumps(context, ensure_ascii=False) + '\nDescribe only actions visible in CURRENT frames. Do not copy background or previous actions, infer completion, or assume continuity over a gap.', context)
