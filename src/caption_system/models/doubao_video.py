"""Ark Files → active file_id → Chat; legacy Base64 remains explicit."""
import base64,copy,json,time,hashlib,shutil,fcntl
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
                 file_poll_interval=2, file_expire_days=7, retry_unknown=False, thinking="disabled", video_cache_root=None):
        super().__init__('doubao',model,0,max_tokens)
        if thinking not in ('enabled','disabled'):raise ValueError('Invalid thinking mode')
        self.thinking=thinking
        self.request_timeout=(30,1800 if thinking=='enabled' else 240)
        self.video_cache_root=Path(video_cache_root) if video_cache_root else None
        if transport not in ('files','base64','auto'):
            raise ValueError('Invalid Ark video transport')
        self.preprocess = video_preprocess(fps,min_frame_tokens,max_frame_tokens,max_video_tokens)
        if transport in ('base64','auto') and len(self.preprocess['video']) > 1:
            raise ValueError('Visual token budgets require Files API transport')
        self.fps=fps
        self.transport=transport
        self.files=ArkFiles(self.key,file_processing_timeout,file_poll_interval,file_expire_days,retry_unknown)

    def _body(self,prompt,video_url):
        return {'model':self.model,'messages':[{'role':'user','content':[
            {'type':'text','text':prompt},{'type':'video_url','video_url':video_url}]}],
            'thinking':{'type':self.thinking},'max_tokens':self.max_tokens,'stream':False}

    def _export(self,task,folder):
        video=Path(folder)/'source_clip.mp4'
        if self.video_cache_root is None:
            return video,export_subsegment(task,video),Path(folder)/'ark_file.json'
        identity={'source_sha256':task.get('source_video_sha256') or sha(task['media_path']),
                  'interval':[task['clip_start_time_s'],task['clip_end_time_s']],
                  'offset':task.get('video_timestamp_offset_s',0),'encoding':'h264-crf18-veryfast-us-v2'}
        key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
        cache=self.video_cache_root/key;cache.mkdir(parents=True,exist_ok=True)
        with (cache/'.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            meta=cache/'export.json';source=cache/'source_clip.mp4'
            if meta.is_file() and source.is_file():
                exported=json.loads(meta.read_text())
                if sha(source)!=exported['sha256']:raise ValueError('Shared video export changed')
            else:
                exported=export_subsegment(task,source);atomic_json(meta,exported)
            if video.exists():
                if sha(video)!=exported['sha256']:raise ValueError('Run video export changed')
            else:
                try:video.hardlink_to(source)
                except OSError:shutil.copyfile(source,video)
        preprocessing=hashlib.sha256(json.dumps(self.preprocess,sort_keys=True).encode()).hexdigest()[:16]
        return video,exported,cache/('ark_file_'+preprocessing+'.json')

    def select_transport(self,video_bytes,prompt):
        empty=self._body(prompt,{'url':'data:video/mp4;base64,','fps':self.fps})
        predicted=len(json.dumps(empty).encode())+4*((video_bytes+2)//3)
        eligible=video_bytes<50_000_000 and predicted<min(self.max_request_bytes,64_000_000)
        if self.transport=='base64' and not eligible:raise ValueError('Video exceeds Base64 file/request limit')
        selected=('base64' if eligible else 'files') if self.transport=='auto' else self.transport
        return selected,predicted

    def prepare_video(self,prompt,task,folder):
        video,exported,file_cache=self._export(task,folder)
        selected,predicted=self.select_transport(exported['bytes'],prompt)
        if selected == 'base64':
            body=self._body(prompt,{'url':'data:video/mp4;base64,'+base64.b64encode(video.read_bytes()).decode(),'fps':self.fps})
        else:
            if exported['bytes']>MAX_FILE_BYTES:raise ValueError('Video exceeds Files API 512 MB project limit')
            body=self._body(prompt,{'file_id':'__ARK_FILE_ID__'})
        path=Path(folder)/'request.json';atomic_json(path,body)
        if path.stat().st_size>=min(self.max_request_bytes,64_000_000):raise ValueError('Video request exceeds configured/provider byte limit')
        return {'path':str(path),'sha256':sha(path),'request_bytes':path.stat().st_size,'image_sizes':[],
            'transport':selected,'transport_policy':self.transport,'estimated_base64_request_bytes':predicted,
            'thinking_enabled':self.thinking=='enabled',
            **({'file_preprocess_configs':self.preprocess,'file_cache_path':str(file_cache)} if selected == 'files' else {}),
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
        usage=extra.get('usage') or {}
        reasoning=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
        total=extra.get('generated_tokens')
        extra.update(thinking_enabled=self.thinking=='enabled',thinking_complete=extra.get('finish_reason')=='stop',
                     caption_complete=bool(text and text.strip()) and extra.get('finish_reason')=='stop',
                     thinking_tokens=reasoning,caption_tokens=(total-reasoning) if total is not None and reasoning is not None and total>=reasoning else None,
                     caption_tokens_note='API total minus reasoning tokens; not a local tokenization of caption',
                     estimated_cost_cny=((extra.get('input_tokens') or 0)*.8+(total or 0)*2.7)/1e6,
                     cost_estimate_note='2026-10-07 standard list rates, no cache discount; invoice is authoritative')
        return text,extra
