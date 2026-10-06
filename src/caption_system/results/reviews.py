"""Camera-specific review validation, reused by the local dashboard."""
from caption_system.config import VERSION
from caption_system.data.tasks import task_id

def validate_review(b, tasks, results):
    if not isinstance(b, dict):
        raise ValueError('Invalid submission')
    for k, limit in [('task_id', 200), ('clip_id', 160), ('camera_id', 16), ('run_id', 100), ('reviewer', 80), ('notes', 2000)]:
        if not isinstance(b.get(k), str) or len(b[k]) > limit:
            raise ValueError('Invalid field ' + k)
    for key in ['clarity','object_accuracy','direction_accuracy','outcome_accuracy']:
        allowed = ['', 'clear','partial','unclear','unknown'] if key == 'clarity' else ['', 'accurate','partial','incorrect','unknown']
        if not isinstance(b.get(key, ''), str) or b.get(key, '') not in allowed:
            raise ValueError('Invalid review dimension ' + key)
    task = tasks.get(b['task_id'])
    if b.get('version') != VERSION or task is None or b['task_id'] != task_id(b['clip_id'], b['camera_id']):
        raise ValueError('Invalid task')
    if not b['reviewer'].strip() or b.get('target') not in ['original', 'model'] or b.get('accuracy') not in ['accurate', 'partial', 'incorrect', 'unknown'] or (b.get('omission') not in ['none', 'yes', 'unknown']):
        raise ValueError('Invalid review options')
    if b['target'] == 'original' and b['run_id']:
        raise ValueError('Original review cannot select a run')
    if b['target'] == 'model' and (not any((r['task_id'] == b['task_id'] and r['run_id'] == b['run_id'] and (r['caption_status'] == 'success') for r in results))):
        raise ValueError('No successful result for this camera and run')
    if b['target'] == 'model':
        result = next(r for r in results if r['task_id'] == b['task_id'] and r['run_id'] == b['run_id'] and r['caption_status'] == 'success')
        if result.get('result_id') and b.get('result_id') != result['result_id']:
            raise ValueError('Result version changed; refresh before submitting review')
    else:
        b['result_id'] = ''
        for key in ['clarity','object_accuracy','direction_accuracy','outcome_accuracy']:
            b[key] = ''
    return b
