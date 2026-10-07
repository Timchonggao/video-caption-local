"""Regression checks for automatic transport, thought parsing and CFS evidence."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from caption_system.models.doubao_video import DoubaoVideo
from caption_system.results.artifacts import resolve_artifact
from caption_system.results.store import RunStore

class V21Tests(unittest.TestCase):
    def test_auto_checks_both_file_and_base64_json_boundaries(self):
        backend=DoubaoVideo('TEST',512,2,transport='auto');backend.max_request_bytes=63_000_000
        self.assertEqual(backend.select_transport(10_000_000,'prompt')[0],'base64')
        self.assertEqual(backend.select_transport(50_000_000,'prompt')[0],'files')
        self.assertEqual(backend.select_transport(48_000_000,'prompt')[0],'files')
        self.assertEqual(backend.select_transport(49_000_000,'x'*2_000_000)[0],'files')
        for size in [0,1,2,3,100]:
            import base64
            body=backend._body('P',{'url':'data:video/mp4;base64,'+base64.b64encode(bytes(size)).decode(),'fps':2})
            self.assertEqual(backend.select_transport(size,'P')[1],len(json.dumps(body).encode()))

    def test_thinking_parses_final_content_and_accounts_reasoning_separately(self):
        backend=DoubaoVideo('TEST',4096,2,transport='auto',thinking='enabled')
        self.assertEqual(backend._body('P',{'file_id':'TEST'})['thinking'],{'type':'enabled'})
        self.assertEqual(backend.request_timeout,(30,1800))
        request={'transport':'base64','image_sizes':[],'video_export':{'source_dimensions':[1600,1300]}}
        with patch.object(backend,'artifacts_valid',return_value=True),patch('caption_system.models.api.Api.generate_prepared',return_value=('Actual final caption.',{'usage':{'completion_tokens_details':{'reasoning_tokens':300}},'input_tokens':1000,'generated_tokens':350,'finish_reason':'stop'})):
            text,extra=backend.generate_prepared(request)
        self.assertEqual(text,'Actual final caption.');self.assertEqual(extra['thinking_tokens'],300)
        self.assertEqual(extra['caption_tokens'],50);self.assertTrue(extra['caption_complete'])
        self.assertAlmostEqual(extra['estimated_cost_cny'],.001745)

    def test_cfs_artifacts_allow_only_configured_run_and_preserve_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cache=root/'cache';runs=root/'runs';config={'artifact_root':str(cache/'release')}
            with patch.dict('caption_system.results.artifacts.PATHS',{'cache_root':str(cache)}):
                store=RunStore('TEST',config,[],runs)
                image=store.root/'artifacts/i/frame.png';image.parent.mkdir();image.write_bytes(b'PNG')
                self.assertTrue((store.root/'artifacts').is_symlink())
                self.assertEqual(resolve_artifact(store.root,'artifacts/i/frame.png'),cache/'release/TEST/i/frame.png')
                (cache/'release/TEST/i/escape.png').symlink_to(root/'outside.png')
                for value in ['/absolute.png','artifacts/../config.json','artifacts/i/escape.png']:
                    with self.assertRaises(ValueError):resolve_artifact(store.root,value)
                self.assertTrue((runs/'TEST/config.json').is_file());store.close()

    def test_off_on_share_export_and_active_file_cache_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'off';folder.mkdir();other=root/'on';other.mkdir()
            source=root/'source.mp4';source.write_bytes(b'ORIGINAL')
            task={'media_path':str(source),'clip_start_time_s':0,'clip_end_time_s':1}
            def export(task,path):
                path.write_bytes(b'EXPORTED')
                from caption_system.results.store import sha
                return {'bytes':8,'sha256':sha(path),'source_dimensions':[64,64],'source_interval_s':[0,1]}
            a=DoubaoVideo('TEST',512,2,transport='files',video_cache_root=root/'cache')
            b=DoubaoVideo('TEST',4096,2,transport='files',thinking='enabled',video_cache_root=root/'cache')
            with patch('caption_system.models.doubao_video.export_subsegment',side_effect=export) as exporter:
                x=a.prepare_video('P',task,folder);y=b.prepare_video('P',task,other)
                self.assertEqual(exporter.call_count,1)
            self.assertEqual(x['file_cache_path'],y['file_cache_path'])
            self.assertEqual(x['video_artifact']['sha256'],y['video_artifact']['sha256'])
            for req in [x,y]:
                body=json.loads(Path(req['path']).read_text())
                self.assertNotIn('temperature',body);self.assertNotIn('top_p',body)
                self.assertEqual(req['file_preprocess_configs'],{'video':{'fps':2}})

class ExportPrecisionTests(unittest.TestCase):
    def test_submillisecond_start_offset_survives_mp4_edit_list(self):
        import av,numpy as np
        from fractions import Fraction
        from caption_system.video.export import export_subsegment
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source.mp4'
            with av.open(str(source),'w') as output:
                stream=output.add_stream('libx264',rate=30);stream.width=stream.height=64;stream.pix_fmt='yuv420p'
                for i in range(30):
                    frame=av.VideoFrame.from_ndarray(np.full((64,64,3),i,dtype=np.uint8),format='rgb24');frame.pts=i;frame.time_base=Fraction(1,30)
                    for packet in stream.encode(frame):output.mux(packet)
                for packet in stream.encode():output.mux(packet)
            exported=export_subsegment({'media_path':str(source),'clip_start_time_s':0,'clip_end_time_s':1,'video_timestamp_offset_s':.000335},root/'clip.mp4')
            self.assertAlmostEqual(exported['encoded_times_s'][0],.000335,places=6)
            self.assertEqual(exported['source_frame_count'],30)

if __name__=='__main__':unittest.main()
