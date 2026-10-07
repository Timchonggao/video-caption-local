import json, tempfile, unittest
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
import av,numpy as np
from caption_system.models.doubao_video import DoubaoVideo
from caption_system.video.export import export_subsegment

class DoubaoVideoTests(unittest.TestCase):
    def test_export_bounds_timestamps_and_video_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'original.mp4'
            with av.open(str(source),'w') as out:
                s=out.add_stream('libx264',rate=10);s.width=s.height=64;s.pix_fmt='yuv420p'
                for i in range(30):
                    f=av.VideoFrame.from_ndarray(np.full((64,64,3),i,dtype=np.uint8),format='rgb24');f.pts=i;f.time_base=Fraction(1,10)
                    for packet in s.encode(f):out.mux(packet)
                for packet in s.encode():out.mux(packet)
            task={'media_path':str(source),'clip_start_time_s':1,'clip_end_time_s':2,'video_timestamp_offset_s':.25}
            exported=export_subsegment(task,root/'export.mp4')
            self.assertFalse(exported['audio']);self.assertTrue(all(1<=p['source_time_s']<2 for p in exported['frames']))
            self.assertEqual(exported['source_frame_count'],10)
            backend=DoubaoVideo('TEST-ONLY',4096,5,transport='base64')
            request=backend.prepare_video('EXACT R3 PROMPT',task,root)
            body=json.loads(Path(request['path']).read_text())
            self.assertEqual(body['thinking'],{'type':'disabled'});self.assertEqual(body['max_tokens'],4096)
            video=body['messages'][0]['content'][1]
            self.assertEqual(video['type'],'video_url');self.assertEqual(video['video_url']['fps'],5)
            self.assertTrue(video['video_url']['url'].startswith('data:video/mp4;base64,'))
            self.assertFalse(request['provider_sampling_known']);self.assertEqual(request['image_sizes'],[])
            self.assertNotIn('Authorization',body);self.assertTrue(backend.artifacts_valid({'request':request}))
            (root/'source_clip.mp4').write_bytes(b'broken')
            self.assertFalse(backend.artifacts_valid({'request':request}))

    def test_invalid_fps_and_budget_are_rejected(self):
        for fps in [0,6,float('nan')]:
            with self.assertRaises(ValueError):DoubaoVideo('TEST-ONLY',512,fps)

    def test_video_config_omits_image_defaults_and_uses_output4096(self):
        from caption_system.pipeline.run import main
        from caption_system.config import PROJECT
        class CapturedConfig(Exception):
            pass
        captured = {}
        def capture(run_id, config, tasks):
            captured.update(config)
            raise CapturedConfig()
        args = ['caption.py', '--run', 'TEST-OUTPUT4096', '--provider', 'doubao',
                '--model', 'TEST-ONLY', '--sample', 'sample_01', '--camera', 'camera2',
                '--input-mode', 'video', '--sampling-fps', '5', '--max-new-tokens', '4096',
                '--prompt', str(PROJECT/'prompts/sample01_v2_r3.txt'), '--background', 'none']
        # Stop before creating a formal run, exporting video or sending a request.
        with patch('sys.argv', args), patch('caption_system.pipeline.run.RunStore', side_effect=capture):
            with self.assertRaises(CapturedConfig):main()
        self.assertNotIn('frames', captured)
        self.assertNotIn('max_pixels', captured)
        self.assertIsNone(captured['frame_max_pixels'])
        self.assertEqual(captured['sampling_fps'], 5)
        self.assertEqual(captured['thinking'], 'disabled')
        self.assertEqual(captured['max_new_tokens'], 4096)
        self.assertEqual(captured['transport'], 'files_api_chat')
        self.assertEqual(captured['file_preprocess_configs'], {'video': {'fps': 5}})

    def test_detailed_http_error_redacts_credentials_no_retry(self):
        from caption_system.models.api import RequestFailure
        backend=DoubaoVideo('TEST-ONLY',512,5);backend.key='TEST-SECRET'
        with patch('requests.post') as post:
            response=post.return_value;response.ok=False;response.status_code=401
            response.json.return_value={'error':{'code':'InvalidKey','message':'bad TEST-SECRET'}}
            with self.assertRaises(RequestFailure) as error:backend._send({},[])
            self.assertNotIn('TEST-SECRET',str(error.exception));self.assertEqual(post.call_count,1)

    def test_entry_forwards_files_budgets_without_running_or_requiring_caption(self):
        import runpy,sys
        from caption_system.config import PROJECT
        entry=runpy.run_path(str(PROJECT/'scripts/run_doubao_video_r3.py'))
        with tempfile.TemporaryDirectory() as tmp:
            config=json.loads((PROJECT/'configs/doubao_seed21_lite_video_r3_files.json').read_text())
            config.update(min_frame_tokens=128,max_frame_tokens=384,max_video_tokens=32768)
            path=Path(tmp)/'config.json';path.write_text(json.dumps(config))
            with patch.object(sys,'argv',['run_doubao_video_r3.py','--config',str(path),'--all']), \
                 patch('subprocess.run') as run:
                entry['main']()
            cmd=run.call_args.args[0]
            for flag,value in [('--video-transport','files'),('--sampling-fps','5'),('--max-new-tokens','4096'),
                               ('--min-frame-tokens','128'),('--max-frame-tokens','384'),('--max-video-tokens','32768')]:
                self.assertEqual(cmd[cmd.index(flag)+1],value)
            self.assertNotIn('--apply',cmd)

    def test_entry_defaults_to_base64_without_generation_overrides(self):
        import runpy,sys
        from caption_system.config import PROJECT
        entry=runpy.run_path(str(PROJECT/'scripts/run_doubao_video_r3.py'))
        with patch.object(sys,'argv',['run_doubao_video_r3.py','--all']), patch('subprocess.run') as run:
            entry['main']()
        cmd=run.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--video-transport')+1],'base64')
        self.assertEqual(cmd[cmd.index('--run')+1],'doubao-seed21-lite-sample01-video-r3')
        self.assertEqual(cmd[cmd.index('--limit')+1],'5')
        for flag in ['--min-frame-tokens','--max-frame-tokens','--max-video-tokens',
                     '--temperature','--top-p','--apply']:
            self.assertNotIn(flag,cmd)

    def test_default_files_archive_selects_its_single_task_without_budgets(self):
        import runpy,sys
        from caption_system.config import PROJECT
        entry=runpy.run_path(str(PROJECT/'scripts/run_doubao_video_r3.py'))
        path=PROJECT/'configs/doubao_files_default_sub01_20261007.json'
        with patch.object(sys,'argv',['run_doubao_video_r3.py','--config',str(path)]), patch('subprocess.run') as run:
            entry['main']()
        cmd=run.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--task-id')+1],'sample_01_seg02_sub01__camera2')
        self.assertEqual(cmd[cmd.index('--video-transport')+1],'files')
        self.assertEqual(cmd[cmd.index('--max-calls')+1],'1')
        for flag in ['--min-frame-tokens','--max-frame-tokens','--max-video-tokens',
                     '--temperature','--top-p','--apply']:
            self.assertNotIn(flag,cmd)
