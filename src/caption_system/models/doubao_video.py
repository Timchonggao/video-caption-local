"""Ark Files → active file_id → Chat; legacy Base64 remains explicit."""
import base64,copy,json,time
from pathlib import Path
from caption_system.models.api import Api
from caption_system.results.atomic import atomic_json
from caption_system.results.store import sha
from caption_system.video.export import export_subsegment
from caption_system.models.ark_files import ArkFiles, FileFailure, MAX_FILE_BYTES, video_preprocess
from caption_system.models.api import RequestFailure


class DoubaoVideo(Api):
    def __init__(self, model, max_tokens, fps, transport='files', min_frame_tokens=None,
                 max_frame_tokens=None, max_video_tokens=None, file_processing_timeout=300,
                 file_poll_interval=2, file_expire_days=7, retry_unknown=False):
        super().__init__('doubao',model,0,max_tokens)
        if transport not in ('files','base64'):
            raise ValueError('Invalid Ark video transport')
        self.preprocess = video_preprocess(fps,min_frame_tokens,max_frame_tokens,max_video_tokens)
        if transport == 'base64' and len(self.preprocess['video']) > 1:
            raise ValueError('Visual token budgets require Files API transport')
        self.fps=fps
        self.transport=transport
        self.files=ArkFiles(self.key,file_processing_timeout,file_poll_interval,file_expire_days,retry_unknown)

    def _body(self,prompt,video_url):
        return {'model':self.model,'messages':[{'role':'user','content':[
            {'type':'text','text':prompt},{'type':'video_url','video_url':video_url}]}],
            'thinking':{'type':'disabled'},'max_tokens':self.max_tokens,'stream':False}

    def prepare_video(self,prompt,task,folder):
        video=Path(folder)/'source_clip.mp4'
        exported=export_subsegment(task,video)
        if self.transport == 'base64':
            if exported['bytes']>=50_000_000:
                raise ValueError('Video file exceeds Base64 50 MB limit')
            body=self._body(prompt,{'url':'data:video/mp4;base64,'+base64.b64encode(video.read_bytes()).decode(),'fps':self.fps})
        else:
            if exported['bytes']>MAX_FILE_BYTES:
                raise ValueError('Video exceeds Files API 512 MB project limit')
            # This immutable template is resolved only during --apply. Preparation
            # has no network side effects and never persists an authorization key.
            body=self._body(prompt,{'file_id':'__ARK_FILE_ID__'})
        path=Path(folder)/'request.json'
        if len(json.dumps(body).encode())>=64_000_000:
            raise ValueError('Video request exceeds 64 MB limit')
        atomic_json(path,body)
        if path.stat().st_size>self.max_request_bytes or path.stat().st_size>=64_000_000:
            raise ValueError('Video request exceeds configured/provider byte limit')
        return {'path':str(path),'sha256':sha(path),'request_bytes':path.stat().st_size,'image_sizes':[],
            'transport':self.transport,
            **({'file_preprocess_configs':self.preprocess,'file_cache_path':str(Path(folder)/'ark_file.json')}
               if self.transport == 'files' else {}),
            'input_mode':'video','requested_fps':self.fps,'provider_sampling_known':False,
            'provider_processed_dimensions_known':False,'video_export':exported,
            'video_artifact':{'path':str(video),'sha256':exported['sha256']},
            'estimated_usage':None,'estimate_note':'Server frame selection, processing resolution and token usage are unknown before response'}

    def artifacts_valid(self,bundle):
        if not super().artifacts_valid(bundle):return False
        video=bundle['request'].get('video_artifact')
        return bool(video and Path(video['path']).is_file() and sha(video['path'])==video['sha256'])

    def generate_prepared(self,request):
        if not self.artifacts_valid({'request':request}):raise ValueError('Prepared video request changed')
        if request.get('transport','base64') == 'files':
            start=time.perf_counter()
            video=request['video_artifact']
            try:
                file_id,metadata=self.files.ensure_ready(video['path'],video['sha256'],
                    request['file_preprocess_configs'],request['file_cache_path'])
            except FileFailure as error:
                error.result_metadata.update(generation_seconds=time.perf_counter()-start,caption_request_seconds=0.0)
                raise
            body=copy.deepcopy(json.loads(Path(request['path']).read_text()))
            part=body['messages'][0]['content'][1]['video_url']
            if part != {'file_id':'__ARK_FILE_ID__'}:
                raise ValueError('Invalid prepared Files request template')
            part['file_id']=file_id
            resolved=Path(request['path']).with_name('resolved_request.json')
            atomic_json(resolved,body)
            metadata.update(model_call_attempted=True,resolved_request_sha256=sha(resolved))
            caption_start=time.perf_counter()
            try:
                text,extra=self._send(body,request['image_sizes'])
            except RequestFailure as error:
                metadata.update(caption_request_seconds=time.perf_counter()-caption_start,generation_seconds=time.perf_counter()-start)
                error.result_metadata=metadata
                raise
            except ValueError:
                metadata.update(caption_request_seconds=time.perf_counter()-caption_start,generation_seconds=time.perf_counter()-start)
                raise FileFailure('Caption response invalid; remote outcome unknown, no automatic retry',
                                  'unknown_remote_outcome',metadata) from None
            extra.update(metadata,caption_request_seconds=extra['generation_seconds'],
                generation_seconds=time.perf_counter()-start,
                timing_note='Files total includes upload, status polling and caption request; individual stage times are recorded.')
        else:
            text,extra=super().generate_prepared(request)
            extra.update(provider_transport='base64',model_call_attempted=True)
        extra.update(input_mode='video',requested_fps=self.fps,provider_sampling_known=False,
            provider_processed_dimensions_known=False,source_video_dimensions=request['video_export']['source_dimensions'])
        return text,extra
