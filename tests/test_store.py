import tempfile, unittest
from pathlib import Path
from caption_system.results.store import RunStore, validate_result
from caption_system.results.reviews import validate_review
from caption_system.config import VERSION

class StoreTests(unittest.TestCase):

    def setUp(self):
        self.tasks = [dict(task_id='s_seg01_sub01__camera' + str(i), clip_id='s_seg01_sub01', camera_id='camera' + str(i), sample_id='s') for i in range(2)]

    def record(self, i=0, status='success'):
        return {**self.tasks[i], 'caption_status': status, 'generated_caption': 'Action' if status == 'success' else ''}

    def test_resume_preserves_other_camera_and_retries_failure(self):
        with tempfile.TemporaryDirectory() as root:
            s = RunStore('test', {}, self.tasks, root)
            s.save(self.record())
            s.save(self.record(1, 'failed'))
            s.close()
            s = RunStore('test', {}, self.tasks, root)
            self.assertEqual([t['camera_id'] for t in s.pending()], ['camera1'])
            self.assertEqual(len(s.records), 2)
            s.close()

    def test_mismatched_camera_rejected(self):
        r = self.record()
        r['camera_id'] = 'camera1'
        with self.assertRaises(ValueError):
            validate_result(r, {t['task_id']: t for t in self.tasks})

    def test_configuration_change_forbidden(self):
        with tempfile.TemporaryDirectory() as root:
            s = RunStore('test', {'prompt': 'a'}, self.tasks, root)
            s.close()
            with self.assertRaises(ValueError):
                RunStore('test', {'prompt': 'b'}, self.tasks, root)

    def test_review_targets_exact_camera(self):
        r = self.record()
        r['run_id'] = 'run'
        b = {**self.tasks[0], 'version': VERSION, 'target': 'model', 'run_id': 'run', 'reviewer': 'A', 'accuracy': 'accurate', 'omission': 'none', 'notes': ''}
        lookup = {t['task_id']: t for t in self.tasks}
        validate_review(b, lookup, [r])
        with self.assertRaises(ValueError):
            validate_review({**b, **self.tasks[1]}, lookup, [r])

    def test_review_cannot_move_to_new_result_version(self):
        r = {**self.record(), 'run_id': 'run', 'result_id': 'new-version'}
        b = {**self.tasks[0], 'version': VERSION, 'target': 'model', 'run_id': 'run', 'result_id': 'old-version', 'reviewer': 'A', 'accuracy': 'accurate', 'omission': 'none', 'notes': ''}
        with self.assertRaises(ValueError):
            validate_review(b, {t['task_id']:t for t in self.tasks}, [r])
        validate_review({**b,'result_id':'new-version'}, {t['task_id']:t for t in self.tasks}, [r])

    def test_hidden_evidence_run_keeps_files_but_not_model_choices(self):
        from caption_system.results.repository import load_runs
        with tempfile.TemporaryDirectory() as root:
            config = {'version': VERSION, 'model_key': 'qwen', 'model_name': 'fixture',
                      'model_label': 'Qwen', 'prompt_id': 'baseline-v2'}
            source = RunStore('qwen-sample01-v2-video-r3', config, self.tasks, root)
            source.save(self.record())
            source.close()
            current = RunStore('official-fixture', {**config, 'experiment_family': 'official-qwen38-v2',
                                                   'official_profile': 'off', 'seed_index': 1}, self.tasks, root)
            current.save(self.record())
            result_id = current.records[self.tasks[0]['task_id']]['result_id']
            current.close()
            runs, results = load_runs(self.tasks, Path(root))
            self.assertEqual([r['id'] for r in runs], ['official-fixture'])
            self.assertEqual(results[0]['result_id'], result_id)
            self.assertTrue((Path(root) / 'qwen-sample01-v2-video-r3/results.jsonl').is_file())

    def test_archived_files_result_keeps_identity_without_web_choice(self):
        from caption_system.results.repository import load_runs
        with tempfile.TemporaryDirectory() as root:
            config = {'version': VERSION, 'model_key': 'doubao', 'model_name': 'fixture',
                      'model_label': '豆包', 'prompt_id': 'baseline-v2'}
            files_id = 'doubao-seed21-lite-sample01-files-default-sub01-20261007'
            archive = RunStore(files_id, config, self.tasks, root)
            archive.save(self.record())
            archive.close()
            base64_id = 'doubao-seed21-lite-sample01-video-r3'
            current = RunStore(base64_id, config, self.tasks, root)
            current.save(self.record())
            result_id = current.records[self.tasks[0]['task_id']]['result_id']
            current.close()
            runs, results = load_runs(self.tasks, Path(root))
            self.assertEqual([r['id'] for r in runs], [base64_id])
            self.assertEqual([(r['run_id'], r['result_id']) for r in results], [(base64_id, result_id)])
            self.assertTrue((Path(root) / files_id / 'results.jsonl').is_file())
