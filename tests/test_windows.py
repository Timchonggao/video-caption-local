import unittest
from caption_system.pipeline.windows import window_tasks
from caption_system.pipeline.prepare import context_data
from caption_system.video.sampling import sample_evidence
import test_harness

class WindowsTests(unittest.TestCase):
    def task(self):
        return dict(task_id='s_seg01_sub01__camera0',clip_id='s_seg01_sub01',sample_id='s',camera_id='camera0',clip_start_time_s=47.,clip_end_time_s=60.,bold_mark='sample',subtask_label='entire task')
    def test_bounds_and_stable_identity(self):
        t=self.task();rows=window_tasks(t,5)
        self.assertEqual([(r['clip_start_time_s'],r['clip_end_time_s']) for r in rows],[(47,52),(52,57),(57,60)])
        self.assertTrue(all(r['parent_task_id']==t['task_id'] for r in rows))
        self.assertEqual(rows,window_tasks(t,5))
        with self.assertRaises(ValueError):window_tasks(t,6)
    def test_background_in_every_window_and_history_reset(self):
        rows=window_tasks(self.task(),5)
        data=context_data(rows[0],None,{},'sample_and_fine_label',True)
        self.assertEqual(data['history']['status'],'first_task')
        prev={'caption_status':'success','result_id':'R1','generated_caption':'Visible'}
        data=context_data(rows[1],rows[0],{rows[0]['task_id']:prev},'sample_and_fine_label',True)
        self.assertEqual(data['history']['result_id'],'R1')
        self.assertEqual(data['background']['fine_label'],'entire task')

class FpsTest(unittest.TestCase):
    setUp = test_harness.HarnessTests.setUp
    tearDown = test_harness.HarnessTests.tearDown
    def test_fps_dedup_real_pts(self):
        frames,meta=sample_evidence(self.tasks[1],4,.4,fps=12)
        self.assertEqual(len(meta),len({m['pts'] for m in meta}))
        self.assertTrue(all(1 <= m['source_time_s'] < 2 for m in meta))
        self.assertEqual(len(frames),len(meta))

class WindowExecutionTests(unittest.TestCase):
    setUp = test_harness.HarnessTests.setUp
    tearDown = test_harness.HarnessTests.tearDown
    def test_budget_resume_and_single_window_passthrough(self):
        from types import SimpleNamespace
        from caption_system.pipeline.windows import execute_windows
        from caption_system.results.store import RunStore,sha
        from caption_system.results.atomic import atomic_json
        import json
        backend=self
        self.calls=0
        def prepare(text,frames,times,folder):
            path=folder/'request.json';atomic_json(path,{'prompt':text})
            return {'path':str(path),'sha256':sha(path),'request_bytes':path.stat().st_size}
        backend.prepare=prepare
        backend.prepare_text=lambda text,folder:prepare(text,[],[],folder)
        backend.artifacts_valid=lambda bundle: True
        def generate(request):
            self.calls+=1
            return json.dumps({'generated_caption':'Visible movement','actions':[],'state_changes':[],'uncertainties':[]}),{'generation_seconds':.01,'finish_reason':'stop'}
        backend.generate_prepared=generate
        cfg={**self.config,'provider':'qwen','max_request_bytes':1024*1024,'sampling_fps':12,'window_seconds':.5,'window_prompt':'window','summary_prompt':'summary','context_missing_policy':'wait_for_predecessor'}
        opts=SimpleNamespace(limit=None,apply=True,rerun=False,max_calls=1,retry_unknown=False)
        parent=RunStore('parent',cfg,[self.tasks[1]],self.root)
        try:
            execute_windows(parent,[self.tasks[1]],cfg,backend,'Prompt',opts)
            self.assertEqual(self.calls,1)
            inputs=list((parent.root/'windows'/self.tasks[1]['task_id']/'inputs').glob('*.json'))
            first=__import__('json').loads(inputs[0].read_text())
            self.assertIn('relative to the CURRENT analysis window start', first['prompt'])
            self.assertFalse(parent.records)
            opts.max_calls=10
            execute_windows(parent,[self.tasks[1]],cfg,backend,'Prompt',opts)
            self.assertEqual(self.calls,3) # two windows, one summary across both invocations
            r=parent.records[self.tasks[1]['task_id']]
            self.assertEqual(r['windows'][1]['previous_result_id'],r['windows'][0]['result_id'])
            execute_windows(parent,[self.tasks[1]],cfg,backend,'Prompt',opts)
            self.assertEqual(self.calls,3)
        finally:parent.close()
