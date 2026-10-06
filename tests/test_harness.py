import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from fractions import Fraction
from types import SimpleNamespace
import av
import numpy as np
from caption_system.pipeline.prepare import prepare, context_data
from caption_system.pipeline.execute import execute
from caption_system.pipeline.context import predecessors
from caption_system.models.api import Api
from caption_system.results.store import RunStore, sha
from caption_system.video.sampling import sample_evidence

class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.video = self.root / 'test.mp4'
        with av.open(str(self.video), 'w') as out:
            stream = out.add_stream('libx264', rate=10)
            stream.width = stream.height = 64
            stream.pix_fmt = 'yuv420p'
            for i in range(30):
                frame = av.VideoFrame.from_ndarray(np.full((64,64,3), i, dtype=np.uint8), format='rgb24')
                frame.pts, frame.time_base = i, Fraction(1,10)
                for packet in stream.encode(frame): out.mux(packet)
            for packet in stream.encode(): out.mux(packet)
        self.tasks = [dict(task_id=f's_seg01_sub0{i+1}__camera0', clip_id=f's_seg01_sub0{i+1}',
                           sample_id='s', camera_id='camera0', media_path=str(self.video),
                           clip_start_time_s=float(i), clip_end_time_s=float(i+1),
                           video_timestamp_offset_s=0.25, bold_mark='Background', subtask_label='Label') for i in range(3)]
        self.config = dict(provider='gemini', background='sample_and_fine_label', contextual=True,
                           context_missing_policy='continue_without_context', frames=4, max_deviation_s=0.4, structured=True)
        self.backend = Api('gemini', 'TEST-NOT-CALLED', 10000, 100)
        self.store = RunStore('test', self.config, self.tasks, self.root)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def record(self, i, parent=None):
        return {**{k:self.tasks[i][k] for k in ('task_id','clip_id','sample_id','camera_id')},
                'caption_status':'success', 'generated_caption':'Visible operation', 'parent_result_id':parent}

    def test_pts_mapping_and_half_open_bounds(self):
        _, evidence = sample_evidence(self.tasks[1], 8, 0.4)
        for e in evidence:
            self.assertTrue(1 <= e['source_time_s'] < 2)
            self.assertAlmostEqual(e['source_time_s'], e['media_time_s'] + 0.25)
            self.assertAlmostEqual(e['relative_time_s'], e['source_time_s'] - 1)
            self.assertIn('pts', e)
        with self.assertRaises(ValueError): sample_evidence(self.tasks[0], 4, 0.01)

    def test_prepared_payload_reused_and_corruption_rebuilt(self):
        first = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        second = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        self.assertEqual(first['input_id'], second['input_id'])
        self.assertEqual(first['request']['sha256'], sha(first['request']['path']))
        Path(first['request']['path']).write_text('broken')
        third = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        self.assertNotEqual(first['input_id'], third['input_id'])

    def test_unrelated_input_frames_are_not_hashed(self):
        first = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        unrelated = {**first, 'preparation_key': 'unrelated',
                     'frames': [{'path': 'must-not-read.png', 'sha256': 'invalid'}]}
        (self.store.root / 'inputs' / '000-unrelated.json').write_text(json.dumps(unrelated))
        actual_sha = sha
        def checked_sha(path):
            self.assertNotEqual(Path(path).name, 'must-not-read.png')
            return actual_sha(path)
        with patch('caption_system.pipeline.prepare.sha', side_effect=checked_sha), \
             patch.object(Path, 'is_file', autospec=True, side_effect=lambda p: self.fail('Unrelated image inspected') if p.name == 'must-not-read.png' else p.exists()):
            second = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        self.assertEqual(first['input_id'], second['input_id'])

    def test_matching_frame_corruption_rebuilds_input(self):
        first = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        (self.store.root / first['frames'][0]['path']).write_bytes(b'corrupt')
        second = prepare(self.store,self.tasks[0],None,self.config,self.backend,'PROMPT',{})
        self.assertNotEqual(first['input_id'], second['input_id'])

    def test_fast_png_preserves_decoded_pixels(self):
        from PIL import Image
        frames, _ = sample_evidence(self.tasks[0], 4, 0.4)
        for i, frame in enumerate(frames):
            path = self.root / f'fast-{i}.png'
            frame.save(path, compress_level=1)
            with Image.open(path) as decoded:
                np.testing.assert_array_equal(np.asarray(frame), np.asarray(decoded))

    def test_fps_dedup_and_cache_identity(self):
        frames, evidence = sample_evidence(self.tasks[0], 12, 0.4, fps=30)
        self.assertEqual(len({e['pts'] for e in evidence}), len(evidence))
        self.assertTrue(all(0 <= e['source_time_s'] < 1 for e in evidence))
        config = {**self.config, 'sampling_fps': 6}
        first = prepare(self.store,self.tasks[0],None,config,self.backend,'PROMPT',{})
        second = prepare(self.store,self.tasks[0],None,{**config, 'sampling_fps': 5},self.backend,'PROMPT',{})
        self.assertNotEqual(first['input_id'],second['input_id'])
        self.assertTrue(first['frames'])

    def test_input_mode_changes_cache_identity(self):
        first = prepare(self.store,self.tasks[0],None,{**self.config,'input_mode':'images'},self.backend,'PROMPT',{})
        second = prepare(self.store,self.tasks[0],None,{**self.config,'input_mode':'video'},self.backend,'PROMPT',{})
        self.assertNotEqual(first['input_id'], second['input_id'])

    def test_stop_on_error_records_failure_without_second_call(self):
        calls = []
        def fail(request):
            calls.append(request)
            raise RuntimeError('simulated resource limit')
        self.backend.generate_prepared = fail
        options = SimpleNamespace(limit=2,apply=True,retry_unknown=False,rerun=False,max_calls=2,stop_on_error=True)
        execute(self.store,self.tasks,predecessors(self.tasks),self.config,self.backend,'PROMPT',options)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(self.store.records),1)
        self.assertEqual(self.store.records[self.tasks[0]['task_id']]['caption_status'],'failed')

    def test_thinking_without_final_caption_is_not_success(self):
        self.backend.generate_prepared = lambda request: ('unfinished thoughts', {'finish_reason':'stop', 'thinking_complete':False, 'caption_complete':False})
        options = SimpleNamespace(limit=1,apply=True,retry_unknown=False,rerun=False,max_calls=1,stop_on_error=True)
        execute(self.store,self.tasks,predecessors(self.tasks),{**self.config,'thinking':True},self.backend,'PROMPT',options)
        result=self.store.records[self.tasks[0]['task_id']]
        self.assertEqual(result['caption_status'],'failed');self.assertEqual(result['output_status'],'missing_final_caption')
        self.assertEqual(result['generated_caption'],'')

    def test_disabled_api_thinking_label_does_not_require_qwen_trace(self):
        self.backend.generate_prepared=lambda request:('Visible operation.',{'finish_reason':'stop'})
        options=SimpleNamespace(limit=1,apply=True,retry_unknown=False,rerun=False,max_calls=1,stop_on_error=True)
        execute(self.store,self.tasks,predecessors(self.tasks),{**self.config,'thinking':'disabled','structured':False},self.backend,'PROMPT',options)
        row=self.store.records[self.tasks[0]['task_id']]
        self.assertEqual(row['caption_status'],'success')
        self.assertEqual(row['generated_caption'],'Visible operation.')

    def test_retest_retains_failed_without_implicit_retry(self):
        self.backend.generate_prepared=lambda request: ('partial',{'finish_reason':'length'})
        config={**self.config,'experiment_family':'official-qwen38-v2'}
        options=SimpleNamespace(limit=2,apply=True,retry_unknown=False,rerun=False,max_calls=2,stop_on_error=True,continue_incomplete=True)
        execute(self.store,self.tasks,predecessors(self.tasks),config,self.backend,'PROMPT',options)
        self.assertEqual(len(self.store.records),2)
        self.backend.generate_prepared=lambda request:self.fail('Failed case retried')
        execute(self.store,self.tasks[:2],predecessors(self.tasks),config,self.backend,'PROMPT',options)

    def test_file_lifecycle_failure_metadata_is_saved(self):
        from caption_system.models.ark_files import FileFailure
        def fail(request):
            raise FileFailure('File processing failed','file_preprocessing_failed',
                              {'model_call_attempted':False,'remote_file':{'id':'file-TEST','status':'failed'},
                               'file_upload_seconds':1.5})
        self.backend.generate_prepared=fail
        options=SimpleNamespace(limit=1,apply=True,retry_unknown=False,rerun=False,max_calls=1,stop_on_error=True)
        execute(self.store,self.tasks,predecessors(self.tasks),self.config,self.backend,'PROMPT',options)
        row=self.store.records[self.tasks[0]['task_id']]
        self.assertEqual(row['caption_status'],'failed')
        self.assertEqual(row['execution_status'],'file_preprocessing_failed')
        self.assertFalse(row['model_call_attempted'])
        self.assertEqual(row['remote_file']['id'],'file-TEST')
        self.assertEqual(row['file_upload_seconds'],1.5)

    def test_pending_history_and_version_changes(self):
        wait = {**self.config, 'context_missing_policy':'wait_for_predecessor'}
        b = prepare(self.store,self.tasks[1],self.tasks[0],wait,self.backend,'PROMPT',{})
        self.assertFalse(b['ready'])
        self.assertIsNone(b['input_fingerprint'])
        self.store.save(self.record(0))
        first = prepare(self.store,self.tasks[1],self.tasks[0],wait,self.backend,'PROMPT',{})
        self.store.save(self.record(0))
        second = prepare(self.store,self.tasks[1],self.tasks[0],wait,self.backend,'PROMPT',{})
        self.assertTrue(first['ready'])
        self.assertNotEqual(first['input_fingerprint'],second['input_fingerprint'])

    def test_transitive_stale_flag_survives_restart_and_history_preserved(self):
        self.store.save(self.record(0))
        parent = self.store.records[self.tasks[0]['task_id']]['result_id']
        self.store.save(self.record(1,parent))
        child = self.store.records[self.tasks[1]['task_id']]['result_id']
        self.store.save(self.record(2,child))
        self.store.save(self.record(0))
        self.store.close()
        self.store = RunStore('test',self.config,self.tasks,self.root)
        self.assertTrue(self.store.records[self.tasks[2]['task_id']]['context_changed'])
        self.assertTrue((self.store.root/'versions'/f'{parent}.json').exists())

    def test_truncated_json_is_not_success_and_resume_does_not_call(self):
        response = json.dumps({'generated_caption':'Action','actions':[],'state_changes':[],'uncertainties':[]})
        self.backend.generate_prepared = lambda request: (response, {'finish_reason':'MAX_TOKENS','usage':{'totalTokenCount':20}})
        options = SimpleNamespace(limit=1,apply=True,retry_unknown=False,rerun=False,max_calls=1)
        execute(self.store,self.tasks,predecessors(self.tasks),self.config,self.backend,'PROMPT',options)
        r = self.store.records[self.tasks[0]['task_id']]
        self.assertEqual(r['output_status'],'truncated')
        self.assertEqual(r['caption_status'],'failed')
        self.assertEqual(r['raw_model_output'],response)
        self.assertEqual(r['usage']['totalTokenCount'],20)

    def test_dry_run_never_calls_provider(self):
        self.backend.generate_prepared = lambda request: self.fail('Provider called')
        options = SimpleNamespace(limit=2,apply=False,retry_unknown=False,rerun=False,max_calls=1)
        execute(self.store,self.tasks,predecessors(self.tasks),self.config,self.backend,'PROMPT',options)
        self.assertFalse(json.loads((self.store.root/'preview.json').read_text())['model_called'])
        self.assertEqual(self.store.records,{})

    def test_unknown_outcome_is_not_implicitly_retried(self):
        self.store.begin(self.tasks[0]['task_id'],'input',remote=True)
        self.store.close()
        self.store = RunStore('test',self.config,self.tasks,self.root)
        self.assertTrue(self.store.uncertain(self.tasks[0]['task_id']))
        self.backend.generate_prepared = lambda request: self.fail('Provider called')
        options = SimpleNamespace(limit=1,apply=True,retry_unknown=False,rerun=False,max_calls=1)
        execute(self.store,[self.tasks[0]],predecessors(self.tasks),self.config,self.backend,'PROMPT',options)
