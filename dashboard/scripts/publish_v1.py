"""Prepare small JPEG evidence and explicitly publish a complete v1 snapshot.

Default: local JPEG preparation and plan only. --apply checks cloud capacity,
uploads missing JPEGs, writes immutable result/evidence records, then switches
publication state. Does not upload videos, tensors or original PNGs; no deletion.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT / 'src'))
from caption_system.config import VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.repository import load_runs
from caption_system.results.store import sha
from cloud_api import query, list_objects
from remote_upload import upload


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='qwen-sample01-v1')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.run):
        parser.error('Invalid run ID')
    folder = PROJECT / 'runs' / args.run
    config = json.loads((folder / 'config.json').read_text())
    tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
    expected = {t['task_id'] for t in tasks if t['sample_id'] == 'sample_01' and (not config.get('camera') or t['camera_id'] == config['camera'])}
    runs, results = load_runs(tasks)
    run = next(r for r in runs if r['id'] == args.run)
    results = [r for r in results if r['run_id'] == args.run]
    if len(expected) != (24 if config.get('camera') == 'camera2' else 144) or {r['task_id'] for r in results} != expected or len(results) != len(expected) or any(r['caption_status'] != 'success' for r in results):
        raise ValueError('Requires complete successful sample01 task domain')
    if run['prompt_id'] not in ('baseline-v1', 'baseline-v2') or config['background'] != 'none' or config['contextual'] or config.get('window_seconds'):
        raise ValueError('Requires current pure-visual baseline')
    if run['prompt_id'] == 'baseline-v2' and (config.get('camera') != 'camera2' or config.get('sampling_fps') != 6):
        raise ValueError('v2 publication requires camera2 at 6 fps')
    output = ROOT / '.local/cloud-sampling' / args.run
    output.mkdir(parents=True, exist_ok=True)
    paths, evidence = {}, []
    index_path = output / 'jpeg-index.json'
    saved_cache = json.loads(index_path.read_text()) if index_path.exists() else {}
    jpeg_cache = {}
    for n, result in enumerate(results, 1):
        record = json.loads((folder / 'versions' / (result['result_id'] + '.json')).read_text())
        input_id = record['input_id']
        bundle = json.loads((folder / 'inputs' / (input_id + '.json')).read_text())
        if bundle['task_id'] != result['task_id'] or not bundle['ready'] or not bundle['frames']:
            raise ValueError('Evidence identity/frame mismatch')
        sizes = bundle.get('request', {}).get('image_sizes', [])
        frames = []
        for i, frame in enumerate(bundle['frames']):
            source = (folder / frame['path']).resolve()
            if not source.is_relative_to(folder.resolve()) or sha(source) != frame['sha256']:
                raise ValueError('Saved frame changed')
            if not bundle['source_interval_s'][0] <= frame['source_time_s'] < bundle['source_interval_s'][1]:
                raise ValueError('Frame outside original interval')
            cached = jpeg_cache.get(frame['sha256'])
            if cached is None:
                cache = output / (frame['sha256'] + '.jpg')
                saved = saved_cache.get(frame['sha256'])
                if saved and cache.is_file() and sha(cache) == saved['sha256']:
                    display_size = saved['display_size']
                else:
                    with Image.open(source) as image:
                        image = image.convert('RGB')
                        image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                        image.save(cache, 'JPEG', quality=75, optimize=True)
                        display_size = list(image.size)
                key = 'sampling/jpeg640-v1/' + sha(cache) + '.jpg'
                cached = key, cache, display_size
                jpeg_cache[frame['sha256']] = cached
            key, cache, display_size = cached
            paths[key] = cache
            frames.append({**{k: frame.get(k) for k in ['requested_relative_time_s', 'relative_time_s', 'source_time_s', 'deviation_s', 'pts', 'time_base', 'duplicate_of', 'size']},
                           'processed_size': sizes[i] if i < len(sizes) else None,
                           'display_size': display_size, 'object_key': key})
        evidence.append({'status': 'result', 'run_id': args.run, 'task_id': result['task_id'], 'result_id': result['result_id'],
                         'input_id': input_id, 'ready': True, 'source_interval_s': bundle['source_interval_s'],
                         'display_profile': 'jpeg640-v1', 'frames': frames})
        if n % 24 == 0:
            print('Prepared evidence', n, '/', len(expected), flush=True)
    index_path.write_text(json.dumps({source_sha: {'sha256': key.rsplit('/',1)[1][:-4], 'display_size': size} for source_sha, (key,path,size) in jpeg_cache.items()}))
    experiment = {'run_id': args.run, 'prompt_id': run['prompt_id'], 'sample': 'sample_01', 'expected_tasks': len(expected),
                  'frames': config['frames'], 'provider': config['provider'], 'model_label': run['model_label']}
    plan = {'run_id': args.run, 'results': len(results), 'frames': sum(len(x['frames']) for x in evidence),
            'jpeg_objects': len(paths), 'jpeg_bytes': sum(p.stat().st_size for p in paths.values()),
            'video_uploads': 0, 'experiment': experiment}
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print('Plan:', json.dumps(plan, ensure_ascii=False), flush=True)
    if not args.apply:
        return
    # Validate dataset and immutable rows before any object upload or publication.
    state = query('SELECT ready FROM cs_datasets WHERE version=?', [VERSION])['results']
    if not state or state[0]['ready'] != 1:
        raise ValueError('Dataset not ready')
    valid = {r['task_id'] for r in query('SELECT task_id FROM cs_tasks WHERE version=?', [VERSION])['results']}
    if not expected <= valid:
        raise ValueError('Cloud task identities differ')
    media = query('SELECT id,object_key FROM cs_media WHERE version=?', [VERSION])['results']
    objects = list_objects()
    existing_objects = {o['key']: int(o['size']) for o in objects}
    if len(media) != 60 or any(m['object_key'] not in existing_objects for m in media):
        raise ValueError('Existing cloud display videos are missing')
    projected = sum(existing_objects.values()) + sum(p.stat().st_size for key, p in paths.items() if key not in existing_objects)
    if projected > 8_000_000_000:
        raise ValueError('Projected R2 bucket exceeds project 8 GB guard')
    print('Projected R2 GB', round(projected / 1e9, 3), 'reused videos', len(media), flush=True)
    public_config = json.dumps({k: v for k, v in run.items() if k != 'id'}, ensure_ascii=False)
    previous = query('SELECT config FROM cs_runs WHERE id=?', [args.run])['results']
    if previous and json.loads(previous[0]['config']) != json.loads(public_config):
        raise ValueError('Run metadata differs')
    previous_results = {r['task_id']: json.loads(r['data']) for r in query('SELECT task_id,data FROM cs_results WHERE version=? AND run_id=?', [VERSION, args.run])['results']}
    for result in results:
        if result['task_id'] in previous_results and previous_results[result['task_id']] != result:
            raise ValueError('Published result differs; new run ID required')
    query((ROOT / 'migrations/0101_sampling_dashboard.sql').read_text())
    old_evidence = {r['task_id']: json.loads(r['data']) for r in query('SELECT task_id,data FROM cs_sampling WHERE version=? AND run_id=?', [VERSION, args.run])['results']}
    if any(e['task_id'] in old_evidence and old_evidence[e['task_id']] != e for e in evidence):
        raise ValueError('Published evidence differs')
    upload({key: path for key, path in paths.items() if key not in existing_objects}, existing_keys=set(existing_objects))
    columns = {r['name'] for r in query('PRAGMA table_info(cs_reviews)')['results']}
    if 'result_id' not in columns:
        query("ALTER TABLE cs_reviews ADD COLUMN result_id TEXT NOT NULL DEFAULT ''")
    query('INSERT INTO cs_runs(id,config) VALUES (?,?) ON CONFLICT(id) DO NOTHING', [args.run, public_config])
    def insert(table, columns, rows):
        for start in range(0, len(rows), 12):
            batch = rows[start:start + 12]
            query('INSERT INTO ' + table + '(' + columns + ') VALUES ' + ','.join('(' + ','.join('?' for _ in row) + ')' for row in batch) + ' ON CONFLICT DO NOTHING', [v for row in batch for v in row])
    insert('cs_results', 'version,task_id,run_id,data', [[VERSION, r['task_id'], args.run, json.dumps(r, ensure_ascii=False)] for r in results])
    insert('cs_sampling', 'version,run_id,task_id,result_id,input_id,data', [[VERSION, args.run, e['task_id'], e['result_id'], e['input_id'], encoded(e)] for e in evidence])
    # Activate only after all evidence and results are available. Old rows are retained.
    old_state = query('SELECT data FROM cs_dashboard WHERE version=?', [VERSION])['results']
    old_publication = json.loads(old_state[0]['data']) if old_state else {}
    publication = {'experiment': old_publication.get('experiment', experiment), 'run_ids': list(dict.fromkeys(old_publication.get('run_ids', []) + [args.run]))}
    query('INSERT INTO cs_dashboard(version,data) VALUES (?,?) ON CONFLICT(version) DO UPDATE SET data=excluded.data', [VERSION, encoded(publication)])
    print('Published complete run; old videos, annotations and reviews retained.', flush=True)

if __name__ == '__main__':
    main()
