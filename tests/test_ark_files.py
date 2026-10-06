import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from caption_system.models.ark_files import ArkFiles, FileFailure, MultipartFile, video_preprocess
from caption_system.models.doubao_video import DoubaoVideo
from caption_system.results.store import sha


def response(body, status=200):
    return SimpleNamespace(ok=status < 400, status_code=status, json=lambda: body,
                           headers={'x-request-id': 'TEST-REQUEST'})


def file_response(status='active', **extra):
    return {'id': 'file-TEST-01', 'status': status, 'mime_type': 'video/mp4',
            'expire_at': int(time.time()) + 86400, **extra}


class ArkFilesTests(unittest.TestCase):
    def test_multipart_stream_matches_length_and_requests_accepts_it(self):
        raw = b'VIDEO' * 20
        body = MultipartFile(io.BytesIO(raw), len(raw), {'purpose': 'user_data', 'preprocess_configs[video][fps]': 5})
        prepared = requests.Request('POST', 'https://example.invalid/files', data=body,
                headers={'Content-Type': 'multipart/form-data; boundary=' + body.boundary}).prepare()
        self.assertIs(prepared.body, body)
        self.assertEqual(int(prepared.headers['Content-Length']), len(body))
        chunks = []
        while chunk := body.read(7):chunks.append(chunk)
        output = b''.join(chunks)
        self.assertEqual(len(output), len(body))
        self.assertIn(raw, output)
        self.assertIn(b'name="preprocess_configs[video][fps]"\r\n\r\n5', output)
        self.assertTrue(output.endswith(('--' + body.boundary + '--\r\n').encode()))

    def test_budget_validation_and_default_omission(self):
        self.assertEqual(video_preprocess(5), {'video': {'fps': 5}})
        for values in [(0,None,None), (True,None,None), (100,50,None), (None,100,50)]:
            with self.assertRaises(ValueError):video_preprocess(5,*values)
        for values in [(384,384,81920), (128,1024,81920), (15,384,81920), (128,641,81920)]:
            with self.assertRaises(ValueError):video_preprocess(5,*values)
        self.assertEqual(video_preprocess(5,128,640,81920)['video']['max_frame_tokens'],640)

    def prepare(self, folder, **options):
        backend = DoubaoVideo('TEST-ONLY', 4096, 5, **options)
        backend.key = backend.files.key = 'TEST-SECRET'
        backend.files.sleep = lambda _: None
        def export(task, path):
            Path(path).write_bytes(b'TEST-MP4-BYTES')
            return {'sha256': sha(path), 'bytes': Path(path).stat().st_size,
                    'source_dimensions': [1600,1300], 'source_frame_count': 150,
                    'source_interval_s': [0,5], 'audio': False}
        with patch('caption_system.models.doubao_video.export_subsegment', side_effect=export), \
             patch('requests.post') as post, patch('requests.get') as get:
            request = backend.prepare_video('SAME R3', {}, folder)
            post.assert_not_called();get.assert_not_called()
        return backend, request

    def test_offline_prepare_then_upload_poll_caption_and_file_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend, request = self.prepare(tmp,min_frame_tokens=128,max_frame_tokens=384,max_video_tokens=32768)
            digest = request['sha256'];uploads=[];captions=[]
            def post(url, **kwargs):
                if url.endswith('/files'):
                    data = kwargs['data'].read();uploads.append(data)
                    self.assertEqual(len(data),int(kwargs['headers']['Content-Length']))
                    self.assertIn(b'name="preprocess_configs[video][max_frame_tokens]"\r\n\r\n384',data)
                    return response(file_response('processing'))
                body=kwargs['json'];captions.append(body)
                self.assertEqual(body['messages'][0]['content'][1]['video_url'], {'file_id':'file-TEST-01'})
                self.assertEqual(body['thinking'],{'type':'disabled'});self.assertEqual(body['max_tokens'],4096)
                self.assertNotIn('temperature',body);self.assertNotIn('top_p',body)
                return response({'model':'TEST-ONLY','choices':[{'message':{'content':'Visible action.'},'finish_reason':'stop'}],
                                 'usage':{'prompt_tokens':1000,'completion_tokens':20}})
            active=file_response(preprocess_configs=request['file_preprocess_configs'])
            with patch('requests.post',side_effect=post), patch('requests.get',side_effect=[
                    response(file_response('processing')),response(active),response(active)]):
                text,stats=backend.generate_prepared(request)
                self.assertEqual(text,'Visible action.');self.assertTrue(stats['preprocessing_echo_verified'])
                self.assertFalse(stats['file_reused']);self.assertTrue(stats['model_call_attempted'])
                _,second=backend.generate_prepared(request)
            self.assertTrue(second['file_reused']);self.assertEqual(len(uploads),1);self.assertEqual(len(captions),2)
            self.assertEqual(sha(request['path']),digest)  # template/fingerprint never changes
            self.assertEqual(json.loads(Path(request['file_cache_path']).read_text())['phase'],'active')
            self.assertNotIn('TEST-SECRET',Path(request['file_cache_path']).read_text())
            self.assertFalse(stats['provider_sampling_known'])
            self.assertIn('file_upload_seconds',stats);self.assertIn('caption_request_seconds',stats)

    def test_processing_failure_blocks_caption_and_redacts_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend,request=self.prepare(tmp)
            with patch('requests.post',return_value=response(file_response('processing'))) as post, \
                 patch('requests.get',return_value=response(file_response('failed',error={'message':'bad TEST-SECRET'}))):
                with self.assertRaises(FileFailure) as error:backend.generate_prepared(request)
            self.assertEqual(post.call_count,1);self.assertEqual(error.exception.execution_status,'file_preprocessing_failed')
            self.assertFalse(error.exception.result_metadata['model_call_attempted'])
            self.assertNotIn('TEST-SECRET',str(error.exception))
            self.assertNotIn('TEST-SECRET',Path(request['file_cache_path']).read_text())

    def test_timeout_retains_file_and_resumes_without_another_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            video=Path(tmp)/'video.mp4';video.write_bytes(b'VIDEO');cache=Path(tmp)/'state.json';now=[0.0]
            client=ArkFiles('TEST-SECRET',processing_timeout=1,poll_interval=.5,
                            clock=lambda:now[0],sleep=lambda seconds:now.__setitem__(0,now[0]+seconds))
            with patch('requests.post',return_value=response(file_response('processing'))) as post, \
                 patch('requests.get',return_value=response(file_response('processing'))):
                with self.assertRaises(FileFailure) as error:client.ensure_ready(video,sha(video),video_preprocess(5),cache)
            self.assertEqual(error.exception.execution_status,'file_processing_timeout')
            self.assertEqual(error.exception.result_metadata['file_processing_seconds'],1)
            self.assertEqual(json.loads(cache.read_text())['file']['id'],'file-TEST-01')
            with patch('requests.post') as post,patch('requests.get',return_value=response(file_response())):
                fid,stats=client.ensure_ready(video,sha(video),video_preprocess(5),cache)
                post.assert_not_called()
            self.assertEqual(fid,'file-TEST-01');self.assertTrue(stats['file_reused'])
            self.assertFalse(stats['preprocessing_echo_verified'])  # no fabricated echo

    def test_unknown_upload_is_not_automatically_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend,request=self.prepare(tmp)
            with patch('requests.post',side_effect=requests.Timeout()) as post:
                for _ in range(2):
                    with self.assertRaises(FileFailure) as error:backend.generate_prepared(request)
                    self.assertEqual(error.exception.execution_status,'unknown_remote_outcome')
                self.assertEqual(post.call_count,1)
            self.assertEqual(json.loads(Path(request['file_cache_path']).read_text())['phase'],'unknown_upload_outcome')

    def test_unknown_upload_requires_explicit_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            video=Path(tmp)/'video.mp4';video.write_bytes(b'VIDEO');cache=Path(tmp)/'state.json';client=ArkFiles('TEST-SECRET')
            with patch('requests.post',side_effect=requests.Timeout()):
                with self.assertRaises(FileFailure):client.ensure_ready(video,sha(video),video_preprocess(5),cache)
            client.retry_unknown=True
            with patch('requests.post',return_value=response(file_response())) as post:
                fid,_=client.ensure_ready(video,sha(video),video_preprocess(5),cache)
            self.assertEqual(fid,'file-TEST-01');self.assertEqual(post.call_count,1)

    def test_caption_timeout_preserves_file_identity_and_stage_timings(self):
        from caption_system.models.api import RequestFailure
        with tempfile.TemporaryDirectory() as tmp:
            backend,request=self.prepare(tmp)
            with patch('requests.post',return_value=response(file_response())) as post, \
                 patch.object(backend,'_send',side_effect=RequestFailure('Caption outcome unknown','unknown_remote_outcome')):
                with self.assertRaises(RequestFailure) as error:backend.generate_prepared(request)
            self.assertEqual(post.call_count,1)
            self.assertTrue(error.exception.result_metadata['model_call_attempted'])
            self.assertEqual(error.exception.result_metadata['remote_file']['id'],'file-TEST-01')
            self.assertIn('caption_request_seconds',error.exception.result_metadata)
            self.assertIn('generation_seconds',error.exception.result_metadata)

    def test_expired_file_and_preprocessing_mismatch_never_call_caption(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend,request=self.prepare(tmp)
            with patch('requests.post',return_value=response(file_response(preprocess_configs={'video':{'fps':1}}))) as post:
                with self.assertRaises(FileFailure) as error:backend.generate_prepared(request)
            self.assertEqual(post.call_count,1);self.assertEqual(error.exception.execution_status,'file_preprocessing_mismatch')
            state=json.loads(Path(request['file_cache_path']).read_text());state['file']['expire_at']=1
            Path(request['file_cache_path']).write_text(json.dumps(state))
            with patch('requests.post') as post,patch('requests.get') as get:
                with self.assertRaises(FileFailure) as error:backend.generate_prepared(request)
                post.assert_not_called();get.assert_not_called()
            self.assertEqual(error.exception.execution_status,'file_unavailable')

    def test_deleted_file_blocks_inference_without_reupload(self):
        with tempfile.TemporaryDirectory() as tmp:
            video=Path(tmp)/'video.mp4';video.write_bytes(b'VIDEO');cache=Path(tmp)/'state.json';client=ArkFiles('TEST-SECRET')
            with patch('requests.post',return_value=response(file_response())):
                client.ensure_ready(video,sha(video),video_preprocess(5),cache)
            with patch('requests.post') as post,patch('requests.get',return_value=response({'error':{}},404)):
                with self.assertRaises(FileFailure) as error:client.ensure_ready(video,sha(video),video_preprocess(5),cache)
                post.assert_not_called()
            self.assertEqual(error.exception.execution_status,'file_unavailable')

    def test_http_error_and_cache_identity_change_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            video=Path(tmp)/'video.mp4';video.write_bytes(b'VIDEO');cache=Path(tmp)/'state.json';client=ArkFiles('TEST-SECRET')
            with patch('requests.post',return_value=response({'error':{'message':'invalid TEST-SECRET'}},401)) as post:
                with self.assertRaises(FileFailure) as error:client.ensure_ready(video,sha(video),video_preprocess(5),cache)
                self.assertEqual(post.call_count,1)
            self.assertNotIn('TEST-SECRET',str(error.exception))
            with patch('requests.post') as post:
                with self.assertRaises(FileFailure) as error:client.ensure_ready(video,sha(video),video_preprocess(4),cache)
                post.assert_not_called()
            self.assertEqual(error.exception.execution_status,'file_identity_failed')

    def test_files_report_reads_only_and_separates_stage_times(self):
        import runpy,sys
        from caption_system.config import PROJECT
        module=runpy.run_path(str(PROJECT/'scripts/report_doubao_files.py'))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'runs/TEST-FILES';(folder/'versions').mkdir(parents=True);(folder/'attempts').mkdir()
            config={'transport':'files_api_chat','model_name':'TEST-ONLY','experiment_task_ids':['task1'],
                    'file_preprocess_configs':video_preprocess(5),'camera':'camera2','sampling_fps':5,
                    'prompt_id':'baseline-v2','thinking':'disabled','max_new_tokens':4096}
            row={'task_id':'task1','result_id':'RESULT','caption_status':'success','generated_caption':'Visible action.',
                 'generation_seconds':9,'file_upload_seconds':2,'file_processing_seconds':3,'caption_request_seconds':4,
                 'input_tokens':1000,'generated_tokens':20}
            (folder/'config.json').write_text(json.dumps(config));(folder/'active.json').write_text(json.dumps({'selection':{'task1':'RESULT'}}));(folder/'versions/RESULT.json').write_text(json.dumps(row))
            module['main'].__globals__['PROJECT']=root
            with patch.object(sys,'argv',['report_doubao_files.py','--run','TEST-FILES']), \
                 patch('requests.post') as post,patch('requests.get') as get:
                module['main']();post.assert_not_called();get.assert_not_called()
            report=json.loads((root/'reports/experiments/TEST-FILES-files-report.json').read_text())
            self.assertEqual(report['success'],1);self.assertEqual(report['quality_status'],'unreviewed')
            self.assertEqual(report['results'][0]['file_processing_seconds'],3)


if __name__ == '__main__':unittest.main()
