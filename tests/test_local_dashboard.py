"""End-to-end HTTP checks against an isolated DB and isolated synthetic run."""
import json, os, socket, subprocess, tempfile, time, unittest, urllib.request, urllib.error
from pathlib import Path
from caption_system.config import PROJECT, VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.store import RunStore

class LocalDashboardTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
        cls.task = tasks[0]
        cls.other = tasks[1]
        config = {'version': VERSION, 'model_key': 'qwen', 'model_name': 'TEST ONLY', 'model_label': 'Qwen', 'prompt_id': 'basic-v1'}
        store = RunStore('TEST-ONLY', config, tasks, cls.root / 'runs')
        store.save({**{k: cls.task[k] for k in ['task_id', 'clip_id', 'sample_id', 'camera_id']}, 'caption_status': 'success', 'generated_caption': 'Test observation', 'input_id': 'TESTINPUT'})
        cls.result_id = store.records[cls.task['task_id']]['result_id']
        folder = store.root / 'artifacts' / 'TESTINPUT'
        folder.mkdir(parents=True)
        import base64, hashlib
        picture = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT5sAAAAASUVORK5CYII=')
        (folder / 'frame_000.png').write_bytes(picture)
        bundle = {'input_id': 'TESTINPUT', 'task_id': cls.task['task_id'], 'ready': True, 'source_interval_s': [0, 8],
                  'frames': [{'path': 'artifacts/TESTINPUT/frame_000.png', 'sha256': hashlib.sha256(picture).hexdigest(), 'relative_time_s': .033, 'requested_relative_time_s': 0, 'source_time_s': .033, 'deviation_s': .033}],
                  'request': {'image_sizes': [[768, 640]], 'path': '/private/request.pt'}}
        (store.root / 'inputs' / 'TESTINPUT.json').write_text(json.dumps(bundle))
        store.close()
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        cls.proc = subprocess.Popen(['python', str(PROJECT / 'scripts/serve_dashboard.py'), '--port', str(port), '--db', str(cls.root / 'reviews.sqlite'), '--runs-root', str(cls.root / 'runs')], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + '/api/clips', timeout=1).close()
                break
            except urllib.error.URLError:
                time.sleep(0.05)
        else:
            raise RuntimeError('Isolated server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.proc.stderr.close()
        cls.tmp.cleanup()

    def request(self, path, body=None, headers=None, method=None):
        request = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers or {}, method=method)
        return urllib.request.urlopen(request, timeout=10)

    def review(self, task=None):
        return {**{k: (task or self.task)[k] for k in ['task_id', 'clip_id', 'camera_id']}, 'version': VERSION, 'target': 'model', 'run_id': 'TEST-ONLY', 'result_id': self.result_id, 'reviewer': 'Test reviewer', 'accuracy': 'accurate', 'omission': 'none', 'notes': 'test'}

    def test_identity_persistence_and_csv(self):
        for name in ['First', 'Second']:
            with self.request('/api/reviews', {**self.review(), 'reviewer': name}) as r:
                self.assertEqual(r.status, 201)
        with self.request('/api/clips') as r:
            data = json.load(r)
        self.assertEqual(len(data['tasks']), 828)
        self.assertEqual(data['reviews'][0]['count'], 2)
        self.assertEqual(data['results'][0]['camera_id'], 'camera0')
        with self.request('/api/reviews/export') as r:
            text = r.read().decode('utf-8-sig')
            self.assertIn('task_id', text)
            self.assertIn('camera0', text)
            self.assertIn('Second', text)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/reviews', self.review(self.other))
        self.assertEqual(error.exception.code, 400)

    def test_media_head_ranges_and_rejection(self):
        path = '/api/media/' + self.task['media_id']
        with self.request(path, method='HEAD') as r:
            self.assertEqual(r.status, 200)
        with self.request(path, headers={'Range': 'bytes=0-255'}) as r:
            self.assertEqual(r.status, 206)
            self.assertEqual(len(r.read()), 256)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request(path, headers={'Range': 'bytes=999999999999-'})
        self.assertEqual(error.exception.code, 416)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/reviews', {})
        self.assertEqual(error.exception.code, 400)

    def test_sampling_evidence_identity_and_frame_access(self):
        from urllib.parse import urlencode
        query = urlencode({'run': 'TEST-ONLY', 'task': self.task['task_id'], 'result': self.result_id})
        with self.request('/api/sampling?' + query) as response:
            evidence = json.load(response)
        self.assertEqual(evidence['status'], 'result')
        self.assertEqual(evidence['result_id'], self.result_id)
        self.assertNotIn('/private', json.dumps(evidence))
        self.assertNotIn('path', evidence['frames'][0])
        self.assertEqual(evidence['frames'][0]['processed_size'], [768, 640])
        with self.request(evidence['frames'][0]['url']) as response:
            self.assertEqual(response.headers['Content-Type'], 'image/png')
            self.assertTrue(response.read().startswith(b'\x89PNG'))
        for fields in [
            {'run': '../TEST-ONLY', 'task': self.task['task_id']},
            {'run': 'TEST-ONLY', 'task': self.other['task_id'], 'result': self.result_id},
        ]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/sampling?' + urlencode(fields))
            self.assertEqual(error.exception.code, 404)
        with self.request('/api/sampling?' + urlencode({'run': 'TEST-ONLY', 'task': self.other['task_id']})) as response:
            self.assertEqual(json.load(response)['status'], 'missing')

    def test_prepared_sampling_without_caption(self):
        from urllib.parse import urlencode
        folder = self.root / 'runs/TEST-ONLY'
        bundle = json.loads((folder / 'inputs/TESTINPUT.json').read_text())
        bundle.update(input_id='PREPARED', task_id=self.other['task_id'])
        (folder / 'inputs/PREPARED.json').write_text(json.dumps(bundle))
        (folder / 'preview.json').write_text(json.dumps({'inputs': [{'task_id': self.other['task_id'], 'input_id': 'PREPARED'}]}))
        try:
            with self.request('/api/sampling?' + urlencode({'run': 'TEST-ONLY', 'task': self.other['task_id']})) as response:
                evidence = json.load(response)
            self.assertEqual(evidence['status'], 'prepared')
            self.assertIsNone(evidence['result_id'])
            self.assertEqual(len(evidence['frames']), 1)
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/sampling/frame?' + urlencode({'run': 'TEST-ONLY', 'task': self.task['task_id'], 'input': 'PREPARED', 'frame': 0}))
            self.assertEqual(error.exception.code, 404)
        finally:
            (folder / 'preview.json').unlink()
            (folder / 'inputs/PREPARED.json').unlink()

    def test_z_quality_dimensions_persist_and_reject_invalid(self):
        import csv, io, sqlite3
        payload = {**self.review(), 'reviewer':'DIMENSION-TEST', 'clarity':'clear',
                   'object_accuracy':'partial','direction_accuracy':'incorrect','outcome_accuracy':'unknown'}
        try:
            with self.request('/api/reviews',payload) as response:
                self.assertEqual(response.status,201)
            with self.request('/api/reviews/export') as response:
                rows=list(csv.DictReader(io.StringIO(response.read().decode('utf-8-sig'))))
            saved=next(r for r in rows if r['reviewer']=='DIMENSION-TEST')
            for key in ['clarity','object_accuracy','direction_accuracy','outcome_accuracy']:
                self.assertEqual(saved[key],payload[key])
            self.assertEqual(saved['result_id'],self.result_id)
            with self.request('/api/clips') as response:
                self.assertIn('quality_dimensions',json.load(response)['review_features'])
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/reviews',{**payload,'clarity':'unsupported'})
            self.assertEqual(error.exception.code,400)
        finally:
            with sqlite3.connect(self.root/'reviews.sqlite') as db:
                db.execute('DELETE FROM task_reviews WHERE reviewer=?',['DIMENSION-TEST'])
