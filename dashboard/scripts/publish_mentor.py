"""Publish the curated mentor view, without videos or inference.

Default prepares JPEGs/plan locally. --apply stages immutable cloud records.
After deploying compatible Pages code, --apply --activate switches visibility.
Previous result rows and publication run IDs are retained.
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
from caption_system.results.sampling_view import sampling_evidence
from caption_system.results.store import sha
from caption_system.results.artifacts import resolve_artifact
from cloud_api import query, list_objects
from remote_upload import upload


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def prepare(config):
    tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
    lookup = {task['task_id']: task for task in tasks}
    expected = set(config['task_ids'])
    if len(expected) != len(config['task_ids']):
        raise ValueError('Duplicate task identities')
    samples=set(config.get('samples') or [config.get('sample')])
    if any(lookup[task]['sample_id'] not in samples or lookup[task]['camera_id'] != config['camera'] for task in expected):
        raise ValueError('Invalid sample/camera scope')
    runs, results = load_runs(tasks)
    output = ROOT / '.local/cloud-sampling/mentor-v2_1' if config.get('published_result_counts') else ROOT / '.local/cloud-sampling/mentor-v2'
    output.mkdir(parents=True, exist_ok=True)
    cache_path = output / 'jpeg-index.json'
    saved = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    images, paths, packets = {}, {}, []
    for run_id in config['run_ids']:
        run = next((r for r in runs if r['id'] == run_id), None)
        all_rows = [r for r in results if r['run_id'] == run_id]
        rows = [r for r in all_rows if r['caption_status'] == 'success']
        if run is None or run['prompt_id'] != config['fixed_prompt_id'] or run['camera'] != config['camera']:
            raise ValueError('Run presentation/scope mismatch: ' + run_id)
        run_scope=set(run.get('experiment_task_ids') or expected)
        target = config.get('published_result_counts', {}).get(run_id, len(run_scope))
        if (not run_scope <= expected or len(rows) != target or len({r['task_id'] for r in rows}) != len(rows)
                or any(r['task_id'] not in run_scope for r in all_rows)
                or (target == len(run_scope) and {r['task_id'] for r in rows} != run_scope)):
            raise ValueError('Incomplete curated run: ' + run_id)
        if target != len(run_scope) and run_id != 'doubao-seed21-lite-full-v2_1-off-r2':
            raise ValueError('Partial publication only permitted for the stopped Doubao off run')
        folder = PROJECT / 'runs' / run_id
        frozen = json.loads((folder / 'config.json').read_text())
        if frozen.get('background') != 'none' or frozen.get('contextual') or frozen.get('window_seconds'):
            raise ValueError('Curated run must be pure visual without history/windows')
        if run['model_key'] == 'qwen' and (run.get('experiment_family') != 'official-qwen38-v2' or run.get('seed_index') != 1):
            raise ValueError('Only retained official seed-one Qwen runs are allowed')
        evidence = []
        for row in rows:
            record = json.loads((folder / 'versions' / (row['result_id'] + '.json')).read_text())
            bundle = json.loads((folder / 'inputs' / (record['input_id'] + '.json')).read_text())
            view = sampling_evidence(PROJECT / 'runs', run_id, row['task_id'], row['result_id'])
            if view['status'] != 'result' or not view['ready']:
                raise ValueError('Sampling evidence not ready')
            if not bundle['frames'] and view.get('provider_sampling_known') is not False:
                raise ValueError('Missing observed sampling frames')
            frames = []
            for index, frame in enumerate(bundle['frames']):
                source = resolve_artifact(folder, frame['path'])
                if sha(source) != frame['sha256']:
                    raise ValueError('Evidence image changed')
                if not bundle['source_interval_s'][0] <= frame['source_time_s'] < bundle['source_interval_s'][1]:
                    raise ValueError('Frame outside original subsegment')
                image = images.get(frame['sha256'])
                if image is None:
                    path = output / (frame['sha256'] + '.jpg')
                    old = saved.get(frame['sha256'])
                    if not old or not path.is_file() or sha(path) != old['sha256']:
                        with Image.open(source) as original:
                            small = original.convert('RGB')
                            small.thumbnail((config['jpeg_max_edge'], config['jpeg_max_edge']), Image.Resampling.LANCZOS)
                            small.save(path, 'JPEG', quality=config['jpeg_quality'], optimize=True)
                            size = list(small.size)
                        old = {'sha256': sha(path), 'display_size': size}
                    image = {**old, 'path': path, 'object_key': 'sampling/jpeg640-v1/' + old['sha256'] + '.jpg'}
                    images[frame['sha256']] = image
                paths[image['object_key']] = image['path']
                info = {k: v for k, v in view['frames'][index].items() if k != 'url'}
                frames.append({**info, 'display_size': image['display_size'], 'object_key': image['object_key']})
            evidence.append({**view, 'display_profile': 'jpeg640-v1', 'frames': frames})
        packets.append({'run': run, 'results': rows, 'evidence': evidence})
    cache_path.write_text(encoded({key: {k: value[k] for k in ['sha256', 'display_size']} for key, value in images.items()}))
    plan = {'run_ids': config['run_ids'], 'results': sum(len(p['results']) for p in packets),
            'results_by_run': {p['run']['id']: len(p['results']) for p in packets},
            'sampling_records': sum(len(p['evidence']) for p in packets),
            'frame_references': sum(len(e['frames']) for p in packets for e in p['evidence']),
            'jpeg_objects': len(paths), 'jpeg_bytes': sum(p.stat().st_size for p in paths.values()),
            'video_uploads': 0, 'fixed_prompt_id': config['fixed_prompt_id']}
    (output / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    return packets, paths, plan


def release_snapshot(packets):
    identities = {packet['run']['id']: {row['task_id']: row['result_id'] for row in packet['results']}
                  for packet in packets}
    return {'identities': identities, 'sha256': hashlib.sha256(encoded(identities).encode()).hexdigest()}


def check_snapshot(path, snapshot, *, require_existing=False):
    if path.is_file():
        if json.loads(path.read_text()) != snapshot:
            raise ValueError('Local published result identities changed after staging')
    elif require_existing:
        raise ValueError('Stage and verify this release before activation')


def cloud_preflight(config, packets, paths):
    """Read D1/R2 only; return exact new-object and new-row counts before staging."""
    ready = query('SELECT ready FROM cs_datasets WHERE version=?', [VERSION])['results']
    if not ready or ready[0]['ready'] != 1:
        raise ValueError('Cloud dataset not ready')
    local_tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
    valid = {r['task_id'] for r in query('SELECT task_id FROM cs_tasks WHERE version=?', [VERSION])['results']}
    if len(valid) != 828 or valid != {r['task_id'] for r in local_tasks}:
        raise ValueError('Cloud task identities differ from 828 local tasks')
    clips = {r['id'] for r in query('SELECT id FROM cs_clips WHERE version=?', [VERSION])['results']}
    local_clips = {r['clip_id'] for r in read_jsonl(PROJECT / 'metadata/clips.jsonl')}
    if len(clips) != 138 or clips != local_clips:
        raise ValueError('Cloud clip identities differ from 138 local clips')
    samples = {r['sample_id'] for r in query('SELECT sample_id FROM cs_samples WHERE version=?', [VERSION])['results']}
    if len(samples) != 10 or (config.get('published_result_counts') and samples != set(config['samples'])):
        raise ValueError('Cloud sample identities differ')
    objects = {o['key']: int(o['size']) for o in list_objects()}
    media = query('SELECT id,object_key FROM cs_media WHERE version=?', [VERSION])['results']
    if len(media) != 60 or len({m['id'] for m in media}) != 60 or any(m['object_key'] not in objects for m in media):
        raise ValueError('Existing low-resolution videos missing')
    new = {key: path for key, path in paths.items() if key not in objects}
    if any(objects[key] != paths[key].stat().st_size for key in paths.keys() & objects.keys()):
        raise ValueError('Existing JPEG object has a different size')
    projected = sum(objects.values()) + sum(p.stat().st_size for p in new.values())
    if projected > config['max_storage_bytes']:
        raise ValueError('Projected R2 size exceeds project 8 GB guard')
    additions = {'runs': 0, 'results': 0, 'sampling': 0}
    for packet in packets:
        run_id = packet['run']['id']
        remote = query('SELECT config FROM cs_runs WHERE id=?', [run_id])['results']
        if remote:
            if json.loads(remote[0]['config']) != {k: v for k, v in packet['run'].items() if k != 'id'}:
                raise ValueError('Published run differs: ' + run_id)
        else:
            additions['runs'] += 1
        for table, source, counter in [('cs_results', 'results', 'results'), ('cs_sampling', 'evidence', 'sampling')]:
            old = {r['task_id']: json.loads(r['data']) for r in query('SELECT task_id,data FROM ' + table + ' WHERE version=? AND run_id=?', [VERSION, run_id])['results']}
            expected = {r['task_id']: r for r in packet[source]}
            if old.keys() - expected.keys() or any(old[tid] != expected[tid] for tid in old.keys() & expected.keys()):
                raise ValueError('Published immutable record differs: ' + run_id)
            additions[counter] += len(expected) - len(old)
    previous_rows = query('SELECT data FROM cs_dashboard WHERE version=?', [VERSION])['results']
    if not previous_rows:
        raise ValueError('Existing mentor presentation missing')
    previous = json.loads(previous_rows[0]['data'])
    if not previous.get('presentation'):
        raise ValueError('Existing presentation missing')
    return {'r2_existing_objects': len(objects), 'r2_existing_bytes': sum(objects.values()),
            'new_jpeg_objects': len(new), 'new_jpeg_bytes': sum(p.stat().st_size for p in new.values()),
            'projected_r2_bytes': projected, 'd1_new': additions, 'video_objects_reused': len(media)}, new, objects, previous


def insert(table, columns, rows):
    for start in range(0, len(rows), 12):
        batch = rows[start:start + 12]
        query('INSERT INTO ' + table + '(' + columns + ') VALUES ' + ','.join('(' + ','.join('?' for _ in row) + ')' for row in batch) + ' ON CONFLICT DO NOTHING', [v for row in batch for v in row])


def apply(config, packets, paths, activate, preflight, new, objects, previous):
    if activate and (preflight['d1_new'] != {'runs': 0, 'results': 0, 'sampling': 0} or new):
        raise ValueError('Stage and verify all data before activation')
    columns = {r['name'] for r in query('PRAGMA table_info(cs_reviews)')['results']}
    for field in ['clarity', 'object_accuracy', 'direction_accuracy', 'outcome_accuracy']:
        if field not in columns:
            query('ALTER TABLE cs_reviews ADD COLUMN ' + field + " TEXT NOT NULL DEFAULT ''")
    print('R2: new JPEG objects', len(new), 'new MB', round(preflight['new_jpeg_bytes'] / 1e6, 2), 'projected GB', round(preflight['projected_r2_bytes'] / 1e9, 3), flush=True)
    upload(new, existing_keys=set(objects))
    for packet in packets:
        run = packet['run'];run_id = run['id']
        query('INSERT INTO cs_runs(id,config) VALUES (?,?) ON CONFLICT DO NOTHING', [run_id, encoded({k: v for k, v in run.items() if k != 'id'})])
        insert('cs_results', 'version,task_id,run_id,data', [[VERSION, r['task_id'], run_id, encoded(r)] for r in packet['results']])
        insert('cs_sampling', 'version,run_id,task_id,result_id,input_id,data', [[VERSION, run_id, e['task_id'], e['result_id'], e['input_id'], encoded(e)] for e in packet['evidence']])
        for table, source in [('cs_results', 'results'), ('cs_sampling', 'evidence')]:
            rows = query('SELECT task_id,data FROM ' + table + ' WHERE version=? AND run_id=?', [VERSION, run_id])['results']
            actual = {r['task_id']: json.loads(r['data']) for r in rows}
            if len(actual) != len(packet[source]) or any(actual.get(r['task_id']) != r for r in packet[source]):
                raise ValueError('Staged rows incomplete; publication unchanged')
    if activate:
        publication = {**previous, 'run_ids': list(dict.fromkeys(previous.get('run_ids', []) + config['run_ids'])),
                       'experiment': {'sample': config.get('sample') or 'all', 'run_id': config['run_ids'][0], 'prompt_id': config['fixed_prompt_id'], 'model_label': 'Qwen 3.8 27B', 'expected_tasks': len(config['task_ids'])},
                       'presentation': {'mode': 'mentor', 'fixed_prompt_id': config['fixed_prompt_id'], 'run_ids': config['run_ids']}}
        query('INSERT INTO cs_dashboard(version,data) VALUES (?,?) ON CONFLICT(version) DO UPDATE SET data=excluded.data', [VERSION, encoded(publication)])
        print('Mentor view activated; old v1 rows and publication registry retained.', flush=True)
    else:
        print('Data staged; deploy Pages code, then run --apply --activate.', flush=True)
    return {'new_jpeg_objects': len(new), 'new_jpeg_bytes': preflight['new_jpeg_bytes'], 'projected_r2_bytes': preflight['projected_r2_bytes'], 'activated': activate}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=PROJECT/'configs/cloud_dashboard_v21.json')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--activate', action='store_true')
    args = parser.parse_args()
    if args.activate and not args.apply:
        parser.error('--activate requires --apply')
    config = json.loads(args.config.read_text())
    packets, paths, plan = prepare(config)
    if config.get('published_result_counts') and (len(packets) != 6 or plan['results'] != 262):
        raise ValueError('Expected exactly six runs and 262 successful results')
    state_dir = ROOT / '.local/cloud-sampling/mentor-v2_1'
    snapshot = release_snapshot(packets)
    snapshot_path = state_dir / 'release-manifest.json'
    check_snapshot(snapshot_path, snapshot, require_existing=args.activate)
    print('Plan:', json.dumps(plan, ensure_ascii=False), flush=True)
    preflight, new, objects, previous = cloud_preflight(config, packets, paths)
    preflight['release_sha256'] = snapshot['sha256']
    (state_dir / 'cloud-preflight.json').write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + '\n')
    print('Cloud preflight:', json.dumps(preflight, ensure_ascii=False), flush=True)
    if args.apply:
        if not snapshot_path.exists():
            snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
        backup = state_dir / 'previous-publication.json'
        if not backup.exists():
            backup.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
        result = apply(config, packets, paths, args.activate, preflight, new, objects, previous)
        (PROJECT / 'reports/cloud/cloud-v21-partial-publication.json').write_text(json.dumps({'plan': plan, 'preflight': preflight, 'publication': result}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
