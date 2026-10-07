"""Atomic, task-keyed run storage shared by Qwen, APIs and external imports."""
import hashlib, json, re, fcntl, uuid, datetime
from pathlib import Path
from caption_system.config import PROJECT
from caption_system.data.tasks import task_id, read_jsonl
from caption_system.results.atomic import atomic_json, atomic_text

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def validate_result(record, tasks):
    tid = record.get('task_id')
    task = tasks.get(tid)
    if task is None or tid != task_id(record.get('clip_id', ''), record.get('camera_id', '')):
        raise ValueError('Unknown or inconsistent task identity')
    if record['clip_id'] != task['clip_id'] or record['camera_id'] != task['camera_id']:
        raise ValueError('Task identity mismatch')
    if record.get('caption_status') not in ['success', 'failed', 'pending']:
        raise ValueError('Invalid caption status')
    if not isinstance(record.get('generated_caption'), str):
        raise ValueError('Caption must be text')
    if record['caption_status'] == 'success' and (not record['generated_caption'].strip()):
        raise ValueError('Empty successful caption')
    return record

class RunStore:

    def __init__(self, name, config, tasks, root=None):
        if not re.fullmatch('[A-Za-z0-9_-]+', name):
            raise ValueError('Invalid run name')
        self.root = Path(root or PROJECT / 'runs') / name
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = (self.root / '.lock').open('w')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.name = name
        self.config = config
        self.tasks = {t['task_id']: t for t in tasks}
        if len(self.tasks) != len(tasks):
            raise ValueError('Duplicate tasks')
        cp = self.root / 'config.json'
        if cp.exists() and json.loads(cp.read_text()) != config:
            raise ValueError('Run configuration changed; choose new run ID')
        atomic_json(cp, config)
        text = ''.join((json.dumps(t, ensure_ascii=False) + '\n' for t in tasks))
        tp = self.root / 'tasks.jsonl'
        if tp.exists() and tp.read_text() != text:
            raise ValueError('Task manifest changed; choose new run ID')
        atomic_text(tp, text)
        from caption_system.results.artifacts import initialize_artifacts
        initialize_artifacts(self.root, config)
        for directory in ('inputs', 'versions', 'attempts'):
            (self.root / directory).mkdir(exist_ok=True)
        self.path = self.root / 'results.jsonl'
        self.records = {}
        if self.path.exists() and not (self.root / 'active.json').exists():
            for r in read_jsonl(self.path):
                validate_result(r, self.tasks)
                if r['task_id'] in self.records:
                    raise ValueError('Duplicate result')
                self.records[r['task_id']] = r
        elif not self.path.exists():
            self.path.touch()
        # Immutable per-result files are the source of truth for new runs.
        # active.json selects versions; results.jsonl is a compatibility projection.
        self.active_path = self.root / 'active.json'
        if self.active_path.exists():
            active = json.loads(self.active_path.read_text())
            selection = active.get('selection', active)
            self.records = {tid: json.loads((self.root / 'versions' / (rid + '.json')).read_text())
                            for tid, rid in selection.items()}
            fp = self.root / 'context_flags.json'
            flags = active.get('flags', json.loads(fp.read_text()) if fp.exists() else {})
            for r in self.records.values():
                r.update(flags.get(r['result_id'], {}))
        for r in self.records.values():
            if not r.get('result_id'):
                r['result_id'] = 'legacy_' + uuid.uuid4().hex
                atomic_json(self.root / 'versions' / (r['result_id'] + '.json'), r)
        self.recover()
        self.log = (self.root / 'run.log').open('a')
        self.metrics()

    def pending(self):
        return [t for t in self.tasks.values() if self.records.get(t['task_id'], {}).get('caption_status') != 'success']

    def event(self, kind, **fields):
        with (self.root / 'events.jsonl').open('a') as out:
            out.write(json.dumps({'event': kind, 'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), **fields}) + '\n')
            out.flush()
            import os
            os.fsync(out.fileno())

    def recover(self):
        for path in (self.root / 'attempts').glob('*.json'):
            value = json.loads(path.read_text())
            if value['state'] == 'running':
                committed = next((r for r in self.records.values() if r.get('attempt_id') == value['attempt_id']), None)
                if committed:
                    value.update(state=committed['caption_status'], result_id=committed['result_id'], execution_status=committed.get('execution_status'))
                    atomic_json(path, value)
                    continue
                value.update(state='interrupted', execution_status='unknown_remote_outcome' if value.get('remote') else 'interrupted')
                atomic_json(path, value)
                self.event('attempt_interrupted', attempt_id=value['attempt_id'], task_id=value['task_id'])

    def begin(self, task_id, input_id, remote=False):
        attempt_id = uuid.uuid4().hex
        atomic_json(self.root / 'attempts' / (attempt_id + '.json'),
                    {'attempt_id': attempt_id, 'task_id': task_id, 'input_id': input_id, 'state': 'running', 'remote': remote})
        return attempt_id

    def uncertain(self, task_id):
        return any(v.get('task_id') == task_id and v.get('execution_status') == 'unknown_remote_outcome' and not v.get('retry_acknowledged')
                   for v in (json.loads(p.read_text()) for p in (self.root / 'attempts').glob('*.json')))

    def acknowledge_unknown(self, task_id):
        for path in (self.root / 'attempts').glob('*.json'):
            value = json.loads(path.read_text())
            if value['task_id'] == task_id and value.get('execution_status') == 'unknown_remote_outcome':
                value['retry_acknowledged'] = True
                atomic_json(path, value)
        self.event('unknown_outcome_retry_acknowledged', task_id=task_id)

    def mark_dependents(self, old_result_id):
        changed = {old_result_id}
        while True:
            found = [r for r in self.records.values() if r.get('parent_result_id') in changed and r.get('result_id') not in changed]
            if not found:
                break
            for r in found:
                r['context_changed'] = True
                r['context_changed_by'] = old_result_id
                changed.add(r['result_id'])
        self.event('context_changed', trigger_result_id=old_result_id, affected=list(changed - {old_result_id}))

    def publish(self):
        flags = {r['result_id']: {'context_changed': True, 'context_changed_by': r.get('context_changed_by')}
                 for r in self.records.values() if r.get('context_changed')}
        atomic_json(self.active_path, {'selection': {tid: r['result_id'] for tid, r in self.records.items()}, 'flags': flags})
        atomic_text(self.path, ''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in self.records.values()))
        atomic_json(self.root / 'context_flags.json', flags)

    def save(self, record):
        validate_result(record, self.tasks)
        record = {**record, 'run_id': self.name, 'result_id': uuid.uuid4().hex}
        old = self.records.get(record['task_id'])
        if old and old.get('result_id'):
            self.mark_dependents(old['result_id'])
        atomic_json(self.root / 'versions' / (record['result_id'] + '.json'), record)
        self.records[record['task_id']] = record
        self.publish()
        if record.get('attempt_id'):
            p = self.root / 'attempts' / (record['attempt_id'] + '.json')
            attempt = json.loads(p.read_text())
            attempt.update(state=record['caption_status'], result_id=record['result_id'], execution_status=record.get('execution_status'))
            atomic_json(p, attempt)
        self.log.write(f'{record['task_id']} {record['caption_status']}\n')
        self.log.flush()
        self.metrics()

    def metrics(self):
        statuses = [r['caption_status'] for r in self.records.values()]
        expected = len(self.config.get('experiment_task_ids') or self.tasks)
        out = {'tasks': expected, 'success': statuses.count('success'), 'failed': statuses.count('failed'), 'pending': expected - statuses.count('success') - statuses.count('failed')}
        atomic_json(self.root / 'metrics.json', out)

    def close(self):
        if hasattr(self, 'log'):
            self.log.close()
        if hasattr(self, 'lock'):
            self.lock.close()

    def __del__(self):
        self.close()
