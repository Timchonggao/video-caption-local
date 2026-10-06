"""Validate all complete camera streams and original-subsegment coverage."""
import json, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from caption_system.config import PROJECT, PATHS
ROOT = PROJECT
inventory = json.loads((ROOT / 'metadata/samples.json').read_text())
rows = [json.loads(l) for l in (ROOT / 'metadata/clips.jsonl').read_text().splitlines()]
base = Path(PATHS['media_root'])
errors = []
jobs = []
sources = 0
for sample in inventory:
    annotation = sample['source_annotation'][0]
    for si, seg in enumerate(annotation['segments_info'], 1):
        for ui, sub in enumerate(seg['sub_segments_info'], 1):
            found = [r for r in rows if r['sample_id'] == sample['sample_id'] and r['segment_index'] == si and (r['subtask_index'] == ui)]
            sources += 1
            if len(found) != 1 or found[0]['clip_start_time_s'] != sub.get('start_time_s', 0) or found[0]['clip_end_time_s'] != sub['end_time_s'] or (found[0]['original_is_success'] != sub.get('is_success', False)):
                errors.append({'source_mapping': sample['sample_id'], 'stage': si, 'sub': ui})
    for m in sample['media']:
        if m['kind'] == 'video':
            jobs.append((sample['sample_id'], m))

def validate(job):
    sid, m = job
    path = base / sid / m['file']
    run = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '2', '-i', str(path), '-f', 'null', '-'], capture_output=True, text=True)
    return {'sample_id': sid, 'camera': m['camera'], 'full_decode_ok': run.returncode == 0 and (not run.stderr), 'error': run.stderr[:2000], 'published_packets': m['published_packets'], 'head_skipped': len(m['skipped_head_packets']), 'original_decoder_errors': len(m['initial_decoder_errors'])}
reports = []
with ThreadPoolExecutor(max_workers=4) as pool:
    for result in pool.map(validate, jobs):
        reports.append(result)
        print('Validated', result['sample_id'], result['camera'], result['full_decode_ok'], flush=True)
report = {'samples': len(inventory), 'cameras': len(reports), 'original_subsegments': sources, 'browser_subsegments': len(rows), 'longest_subsegment_s': max((r['clip_duration_s'] for r in rows)), 'original_false_included': sum((not r['original_is_success'] for r in rows)), 'mapping_errors': errors, 'camera_results': reports, 'status': 'pass' if not errors and all((r['full_decode_ok'] for r in reports)) else 'review_required'}
(ROOT / 'reports/data-checks').mkdir(parents=True, exist_ok=True)
(ROOT / 'reports/data-checks/mcap-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('Validation', report['status'], flush=True)
