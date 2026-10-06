"""Local dashboard API. Videos stay on CFS, task-keyed reviews stay on overlay."""
import argparse, csv, io, json, mimetypes, re, sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote, parse_qs
from caption_system.config import PROJECT, PATHS, VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.repository import load_runs
from caption_system.results.reviews import validate_review
from caption_system.results.sampling_view import sampling_evidence, sampling_frame
REVIEW_KEYS = ['id', 'version', 'task_id', 'clip_id', 'camera_id', 'target', 'run_id', 'reviewer', 'accuracy', 'omission', 'notes', 'result_id', 'clarity', 'object_accuracy', 'direction_accuracy', 'outcome_accuracy', 'created_at']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18788)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--runs-root', type=Path)
    args = parser.parse_args()
    root = PROJECT / 'dashboard'
    clips = read_jsonl(PROJECT / 'metadata/clips.jsonl')
    tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
    lookup = {t['task_id']: t for t in tasks}
    inventories = {r['sample_id']: r for r in json.loads((PROJECT / 'metadata/samples.json').read_text())}
    media = {m['id']: Path(PATHS['media_root']) / r['sample_id'] / m['file'] for r in inventories.values() for m in r['media'] if m['kind'] == 'video'}
    dbpath = args.db or root / '.local/reviews.sqlite'
    dbpath.parent.mkdir(exist_ok=True)

    def connect():
        db = sqlite3.connect(dbpath)
        db.row_factory = sqlite3.Row
        return db
    with connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS task_reviews(id INTEGER PRIMARY KEY,version TEXT,task_id TEXT,clip_id TEXT,camera_id TEXT,target TEXT,run_id TEXT,reviewer TEXT,accuracy TEXT,omission TEXT,notes TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
        db.execute('CREATE INDEX IF NOT EXISTS task_review_lookup ON task_reviews(version,task_id,target,run_id)')
        if 'result_id' not in {r[1] for r in db.execute('PRAGMA table_info(task_reviews)')}:
            db.execute("ALTER TABLE task_reviews ADD COLUMN result_id TEXT DEFAULT ''")

        columns = {r[1] for r in db.execute('PRAGMA table_info(task_reviews)')}
        for field in ['clarity', 'object_accuracy', 'direction_accuracy', 'outcome_accuracy']:
            if field not in columns:
                db.execute(f"ALTER TABLE task_reviews ADD COLUMN {field} TEXT DEFAULT ''")

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, *args):
            pass

        def send_body(self, body, status=200, content_type='application/json; charset=utf-8', headers=None):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def send_json(self, value, status=200):
            self.send_body(json.dumps(value, ensure_ascii=False).encode(), status)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            try:
                self.get()
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                print(type(e).__name__, str(e), flush=True)
                self.send_json({'error': '服务读取失败，请检查数据和结果格式'}, 500)

        def get(self):
            path = unquote(urlparse(self.path).path)
            if path == '/api/clips':
                runs, results = load_runs(tasks, args.runs_root)
                with connect() as db:
                    reviews = [dict(r) for r in db.execute('SELECT task_id,clip_id,camera_id,target,run_id,result_id,COUNT(*) AS count FROM task_reviews WHERE version=? GROUP BY task_id,clip_id,camera_id,target,run_id,result_id', [VERSION])]
                return self.send_json({'version': VERSION, 'clips': [{k: v for k, v in c.items() if k not in ['mcap_path', 'media_path']} for c in clips], 'tasks': [{k: t[k] for k in ['task_id', 'clip_id', 'sample_id', 'camera_id', 'media_id']} for t in tasks], 'runs': runs, 'results': results, 'reviews': reviews, 'review_features': ['quality_dimensions'], 'experiment': {**{k: v for k, v in json.loads((PROJECT / 'configs/sample01_v1.json').read_text()).items() if k in ['run_id', 'prompt_id', 'sample', 'expected_tasks', 'frames', 'provider']}, 'model_label': json.loads((PROJECT / 'configs/models.json').read_text())['qwen']['label']}})
            if path == '/api/sampling':
                query = parse_qs(urlparse(self.path).query)
                try:
                    task = query.get('task', [''])[0]
                    if task not in lookup:
                        raise ValueError('Unknown task')
                    evidence = sampling_evidence(args.runs_root or PROJECT / 'runs', query.get('run', [''])[0], task, query.get('result', [None])[0])
                    return self.send_json(evidence)
                except (ValueError, KeyError, FileNotFoundError):
                    return self.send_json({'error': '采样输入尚未保存或无法读取'}, 404)
            if path.startswith('/api/sample-details/'):

                inv = inventories.get(path.rsplit('/', 1)[-1])
                if inv is None:
                    return self.send_json({'error': '样本不存在'}, 404)
                return self.send_json({'sample_id': inv['sample_id'], 'media': [{k: v for k, v in m.items() if k != 'file'} for m in inv['media'] if m['kind'] == 'video']})
            if path.startswith('/api/annotations/'):
                sid = path.rsplit('/', 1)[-1]
                if sid not in inventories:
                    return self.send_json({'error': '样本不存在'}, 404)
                return self.send_json(json.loads((PROJECT / 'metadata/annotations' / f'{sid}.json').read_text()))
            if path == '/api/reviews/export':
                with connect() as db:
                    records = [dict(r) for r in db.execute('SELECT * FROM task_reviews WHERE version=? ORDER BY id', [VERSION])]
                output = io.StringIO()
                writer = csv.DictWriter(output, fieldnames=REVIEW_KEYS)
                writer.writeheader()
                for record in records:
                    writer.writerow({k: "'" + v if isinstance(v, str) and re.match('^\\s*[=+@-]', v) else v for k, v in record.items()})
                return self.send_body(('\ufeff' + output.getvalue()).encode(), content_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="reviews.csv"'})
            if path == '/api/sampling/frame':
                query = parse_qs(urlparse(self.path).query)
                try:
                    task = query.get('task', [''])[0]
                    if task not in lookup:
                        raise ValueError('Unknown task')
                    file = sampling_frame(args.runs_root or PROJECT / 'runs', query.get('run', [''])[0], task, query.get('input', [''])[0], int(query.get('frame', ['-1'])[0]))
                except (ValueError, KeyError, FileNotFoundError):
                    return self.send_json({'error': '采样帧不存在或已改变'}, 404)
            elif path.startswith('/api/media/'):
                file = media.get(path.rsplit('/', 1)[-1])
            elif path.startswith('/api/'):
                return self.send_json({'error': '接口不存在'}, 404)
            else:
                file = (root / 'dist' / path.lstrip('/')).resolve()
                if not file.is_relative_to((root / 'dist').resolve()):
                    return self.send_json({'error': '路径无效'}, 403)
                if not file.is_file():
                    file = root / 'dist/index.html'
            if file is None or not file.is_file():
                return self.send_json({'error': '文件不存在'}, 404)
            size = file.stat().st_size
            start, end = (0, size - 1)
            status = 200
            value = self.headers.get('Range')
            if value:
                match = re.fullmatch('bytes=(\\d*)-(\\d*)', value)
                if not match or not any(match.groups()):
                    return self.send_body(b'', 416, headers={'Content-Range': f'bytes */{size}'})
                if match[1]:
                    start = int(match[1])
                    end = min(int(match[2]) if match[2] else end, end)
                else:
                    start = max(0, size - int(match[2]))
                if start > end or start >= size:
                    return self.send_body(b'', 416, headers={'Content-Range': f'bytes */{size}'})
                status = 206
            self.send_response(status)
            self.send_header('Content-Type', mimetypes.guess_type(str(file))[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            if status == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            with file.open('rb') as stream:
                stream.seek(start)
                left = end - start + 1
                while left:
                    body = stream.read(min(left, 65536))
                    if not body:
                        break
                    self.wfile.write(body)
                    left -= len(body)

        def do_POST(self):
            if urlparse(self.path).path != '/api/reviews':
                return self.send_json({'error': '接口不存在'}, 404)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('Invalid size')
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + self.headers.get('Host', ''):
                    return self.send_json({'error': '来源无效'}, 403)
                b = json.loads(self.rfile.read(length))
                _, results = load_runs(tasks, args.runs_root)
                validate_review(b, lookup, results)
                with connect() as db:
                    db.execute('INSERT INTO task_reviews(version,task_id,clip_id,camera_id,target,run_id,reviewer,accuracy,omission,notes,result_id,clarity,object_accuracy,direction_accuracy,outcome_accuracy) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [b.get(k, '').strip() if k == 'reviewer' else b.get(k, '') for k in REVIEW_KEYS[1:-1]])
                return self.send_json({'saved': True}, 201)
            except (ValueError, TypeError):
                return self.send_json({'error': '请检查任务、相机、评价选项和模型结果'}, 400)
    print(f'Server-local dashboard http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
if __name__ == '__main__':
    main()
