"""Read-only smoke check for the activated public v2.1 mentor dashboard."""
import argparse
import json
import urllib.request
from collections import Counter
from urllib.parse import urlencode

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url', default='https://video-caption-dashboard.pages.dev')
args = parser.parse_args()
base = args.url.rstrip('/')


def fetch(path, headers=None, method='GET'):
    request = urllib.request.Request(base + path, headers={'User-Agent': 'curl/8.0.0', **(headers or {})}, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.status, dict(response.headers), response.read()


def get(path):
    status, _, body = fetch(path)
    assert status == 200, (path, status)
    assert b'/root/' not in body and b'/mnt/cfs/' not in body, (path, 'server path leaked')
    return json.loads(body)


payload = get('/api/clips')
assert payload['presentation'] == {'mode': 'mentor', 'fixed_prompt_id': 'baseline-v2-1'}
assert len(payload['clips']) == 138 and len(payload['tasks']) == 828
assert len({c['sample_id'] for c in payload['clips']}) == 10
runs = {r['id']: r for r in payload['runs']}
assert len(runs) == 6 and all(r['release_id'] == 'v2_1' for r in runs.values())
results = payload['results']
assert len(results) == 262
assert all(r['caption_status'] == 'success' and r['camera_id'] == 'camera2' and r['run_id'] in runs for r in results)
assert Counter(r['run_id'] for r in results) == {
    'qwen-full-v2_1-off-r2': 138,
    'qwen-full-v2_1-low-r2': 10,
    'qwen-full-v2_1-medium-r2': 10,
    'qwen-full-v2_1-xhigh-r2': 10,
    'doubao-seed21-lite-full-v2_1-off-r2': 84,
    'doubao-seed21-lite-full-v2_1-on-r2': 10,
}
first = {sample: min((c for c in payload['clips'] if c['sample_id'] == sample),
                     key=lambda c: (c['clip_start_time_s'], c['clip_end_time_s'], c['clip_id']))['clip_id']
         for sample in {c['sample_id'] for c in payload['clips']}}
assert all({r['clip_id'] for r in results if r['run_id'] == run_id} == set(first.values())
           for run_id in runs if run_id not in ('qwen-full-v2_1-off-r2', 'doubao-seed21-lite-full-v2_1-off-r2'))
assert not any(r['task_id'] == 'sample_07_seg01_sub03__camera2' and r['run_id'] == 'doubao-seed21-lite-full-v2_1-off-r2' for r in results)
for sample, clip in sorted(first.items()):
    inventory = get('/api/sample-details/' + sample)
    assert {m['camera'] for m in inventory['media']} == {f'camera{i}' for i in range(6)}
    for media in inventory['media']:
        status, headers, body = fetch('/api/media/' + media['id'], {'Range': 'bytes=0-31'})
        assert status == 206 and len(body) == 32 and headers.get('Content-Type') == 'video/mp4'
    annotation = get('/api/annotations/' + sample)
    assert isinstance(annotation, list) and annotation and 'segments_info' in annotation[0]
    row = next(r for r in results if r['clip_id'] == clip and r['run_id'] == 'qwen-full-v2_1-off-r2')
    view = get('/api/sampling?' + urlencode({'run': row['run_id'], 'task': row['task_id'], 'result': row['result_id']}))
    assert view['frames'] and view['status'] == 'result'
    status, headers, _ = fetch(view['frames'][0]['url'], method='HEAD')
    assert status == 200 and headers.get('Content-Type') == 'image/jpeg'
status, _, body = fetch('/api/reviews/export')
assert status == 200 and b'result_id' in body and b'run_id' in body
print(json.dumps({'status': 'ok', 'samples': 10, 'clips': 138, 'tasks': 828,
                  'runs': 6, 'results': 262, 'videos_range_checked': 60,
                  'sampling_images_checked': 10, 'reviews_csv': True}, ensure_ascii=False))
