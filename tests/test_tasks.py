import json, unittest
from caption_system.config import PROJECT
from caption_system.data.tasks import build_tasks, read_jsonl
from caption_system.pipeline.context import build_context, predecessors, ordered

class TasksTests(unittest.TestCase):

    def setUp(self):
        self.tasks = build_tasks(read_jsonl(PROJECT / 'metadata/clips.jsonl'), json.loads((PROJECT / 'metadata/samples.json').read_text()))

    def test_all_original_intervals_and_cameras(self):
        self.assertEqual(len(self.tasks), 828)
        self.assertEqual(len({t['task_id'] for t in self.tasks}), 828)
        false = [t for t in self.tasks if not t['original_is_success']]
        self.assertEqual(len(false), 6)
        for t in self.tasks:
            self.assertTrue(t['media_path'].endswith(t['camera_id'] + '.mp4'))
        self.assertTrue(any((t['clip_duration_s'] > 30 for t in self.tasks)))

    def test_camera_scoped_predecessors(self):
        prev = predecessors(self.tasks)
        for t in self.tasks:
            p = prev[t['task_id']]
            if p:
                self.assertEqual((t['sample_id'], t['camera_id']), (p['sample_id'], p['camera_id']))
        row = self.tasks[0]
        other = {**row, 'camera_id': 'camera1'}
        with self.assertRaises(ValueError):
            build_context(row, other, {})

    def test_only_previous_visible_caption(self):
        row = ordered(self.tasks)[1]
        p = predecessors(self.tasks)[row['task_id']]
        _, context = build_context(row, p, {p['task_id']: {'caption_status': 'success', 'generated_caption': 'Visible action'}})
        self.assertEqual(context['previous_generated_caption'], 'Visible action')
        self.assertNotIn('subtask_label', context)
