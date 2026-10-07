"""The v3 pilot changes window scope, not v2.1 parameters or raw labels."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'scripts'))
import run_v3_window_off as pilot


class V3WindowPilotTests(unittest.TestCase):
    def test_scope_and_frozen_baseline(self):
        spec = json.loads(pilot.SPEC_PATH.read_text())
        tasks = pilot.selected_tasks()
        config, prompt, summary = pilot.configuration(spec, tasks)
        windows = [pilot.window_tasks(task, 5) for task in tasks]
        self.assertEqual(len(tasks), 10)
        self.assertEqual(sum(map(len, windows)), 17)
        self.assertEqual(sum(len(rows) > 1 for rows in windows), 5)
        self.assertEqual(config['sampling_fps'], 2)
        self.assertEqual(config['input_mode'], 'video')
        self.assertEqual(config['max_new_tokens'], 4096)
        self.assertEqual(config['caption_max_tokens'], 512)
        self.assertEqual(config['frame_max_pixels'], 512000)
        self.assertEqual(config['background'], 'none')
        self.assertFalse(config['contextual'])
        self.assertFalse(config['structured'])
        self.assertEqual(config['window_history'], 'none')
        self.assertIn('one analysis window', prompt)
        self.assertIn('fallible evidence', summary)
        self.assertNotIn('fine_label', prompt + summary)
        for task, rows in zip(tasks, windows):
            self.assertEqual(rows[0]['clip_start_time_s'], task['clip_start_time_s'])
            self.assertEqual(rows[-1]['clip_end_time_s'], task['clip_end_time_s'])
            for left, right in zip(rows, rows[1:]):
                self.assertEqual(left['clip_end_time_s'], right['clip_start_time_s'])

    def test_input_audit_rejects_duplicate_or_outside_pts(self):
        row = {'window_id': 'W', 'clip_start_time_s': 5, 'clip_end_time_s': 10}
        frame = {'source_time_s': 5.1, 'pts': 3, 'sha256': 'sha'}
        request = {'input_mode': 'video', 'do_sample_frames': False, 'do_resize': False,
                   'image_count': 1, 'image_sizes': [[512, 512]], 'temporal_evidence': {}}
        bundle = {'ready': True, 'frames': [frame], 'request': request, 'input_id': 'I'}
        self.assertEqual(pilot.audit_input(bundle, row)['real_frames'], 1)
        with self.assertRaisesRegex(ValueError, 'half-open'):
            pilot.audit_input({**bundle, 'frames': [{**frame, 'source_time_s': 10}]}, row)
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            pilot.audit_input({**bundle, 'frames': [frame, {**frame, 'source_time_s': 5.2}],
                               'request': {**request, 'image_count': 2}}, row)
        with self.assertRaisesRegex(ValueError, 'resampled'):
            pilot.audit_input({**bundle, 'request': {**request, 'do_sample_frames': True}}, row)

    def test_summary_uses_only_window_captions_and_checks_completion(self):
        class Parent:
            def __init__(self, root):
                self.root = root
                self.saved = []
            def begin(self, *args, **kwargs):
                return 'attempt'
            def save(self, record):
                self.saved.append(record.copy())

        class Backend:
            def prepare_text(self, text, folder):
                self.text = text
                return {'request_bytes': 10, 'path': str(folder / 'summary_inputs.pt')}
            def generate_prepared(self, request):
                self.request = request
                return 'The person moves the garment, then sets it down.', {
                    'generation_seconds': 1, 'input_tokens': 50, 'generated_tokens': 12,
                    'finish_reason': 'stop', 'caption_complete': True}

        with tempfile.TemporaryDirectory() as tmp:
            parent = Parent(Path(tmp))
            backend = Backend()
            task = {'task_id': 'sample__camera2'}
            record = {'windows': [{'window_id': 'w1', 'source_interval_s': [0, 5],
                                   'generated_caption': 'The person moves a garment.', 'annotation': {'fine_label': 'secret'}},
                                  {'window_id': 'w2', 'source_interval_s': [5, 8],
                                   'generated_caption': 'The garment is set down.'}],
                      'window_result_ids': ['r1', 'r2'], 'generation_seconds': 2,
                      'input_tokens': 100, 'generated_tokens': 20,
                      'caption_status': 'success', 'generated_caption': ''}
            pilot.summarize(parent, task, record, backend, 'Summarize supported actions.',
                            {'max_request_bytes': 100, 'config': 'frozen'})
            self.assertEqual(parent.saved[0]['caption_status'], 'success')
            self.assertEqual(parent.saved[0]['summary_source_result_ids'], ['r1', 'r2'])
            self.assertEqual(parent.saved[0]['generation_seconds'], 3)
            self.assertNotIn('fine_label', backend.text)
            self.assertEqual(backend.request['task_id'], 'sample__camera2__summary')


if __name__ == '__main__':
    unittest.main()
