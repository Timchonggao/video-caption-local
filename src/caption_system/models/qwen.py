"""Qwen backend: persistent model, explicit timestamped images, local weights only."""
import time
from pathlib import Path
from caption_system.results.store import sha

class Qwen:

    def __init__(self, path, max_pixels, max_tokens, input_mode="images", sampling_fps=None, thinking=False, trace_tokens=False, caption_max_tokens=None, sampling=None, reasoning_effort=None, preserve_thinking=None):
        import torch
        from transformers import AutoProcessor
        self.torch = torch
        self.max_pixels = max_pixels
        self.max_tokens = max_tokens
        self.input_mode = input_mode
        self.sampling_fps = sampling_fps
        self.thinking = thinking
        self.trace_tokens = trace_tokens
        self.caption_max_tokens = caption_max_tokens
        self.sampling = sampling
        self.reasoning_effort = reasoning_effort
        self.preserve_thinking = preserve_thinking
        self.current_task_id = None
        self.prepared_metadata = {}
        torch.manual_seed(0)
        self.path = path
        self.processor = AutoProcessor.from_pretrained(path, local_files_only=True)
        self.model = None
        self.runtime = {'torch': torch.__version__, 'transformers': __import__('transformers').__version__, 'cpu_threads': torch.get_num_threads()}

    def _template_kwargs(self):
        result={'enable_thinking':self.thinking}
        if self.reasoning_effort is not None:result['reasoning_effort']=self.reasoning_effort
        if self.preserve_thinking is not None:result['preserve_thinking']=self.preserve_thinking
        return result

    def _load(self):
        if self.model is not None:
            return
        from transformers import AutoModelForMultimodalLM
        torch = self.torch
        if not torch.cuda.is_available():
            raise RuntimeError('CUDA unavailable; GPU inference not attempted on CPU')
        start = time.perf_counter()
        path = self.path
        self.model = AutoModelForMultimodalLM.from_pretrained(path, local_files_only=True, dtype=torch.bfloat16, device_map='auto', max_memory={i: '75GiB' for i in range(torch.cuda.device_count())})
        self.model.eval()
        torch.cuda.synchronize()
        self.runtime.update(model_load_seconds=time.perf_counter() - start, model_class=type(self.model).__name__)

    def _inputs(self, prompt, frames, times):
        content = [{'type': 'text', 'text': prompt}]
        for frame, t in zip(frames, times):
            content.extend([{'type': 'text', 'text': f'Frame at {t:.6f} seconds:'}, {'type': 'image', 'image': frame}])
        return self.processor.apply_chat_template([{'role': 'user', 'content': content}], tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors='pt', **self._template_kwargs(), processor_kwargs={'images_kwargs': {'size': {'longest_edge': self.max_pixels, 'shortest_edge': 4096}}})

    def _video_inputs(self, prompt, frames, times):
        import re
        import types
        import numpy as np
        from transformers.image_utils import SizeDict
        from transformers.video_utils import VideoMetadata
        from caption_system.video.temporal import temporal_evidence
        torch = self.torch
        ip = self.processor.image_processor
        vp = self.processor.video_processor
        if not self.sampling_fps or ip.patch_size != vp.patch_size or ip.merge_size != vp.merge_size:
            raise ValueError('Unsupported video processor configuration')
        pixels = torch.stack([torch.from_numpy(np.array(f)).permute(2, 0, 1) for f in frames])
        resized = ip.resize(pixels, SizeDict(shortest_edge=4096, longest_edge=self.max_pixels),
                            ip.resample, factor=ip.patch_size * ip.merge_size)
        target = [resized.shape[-1], resized.shape[-2]]
        timing = temporal_evidence(times, vp.temporal_patch_size)
        content = [{'type': 'text', 'text': prompt}, {'type': 'video'}]
        text = self.processor.apply_chat_template([{'role': 'user', 'content': content}],
                    tokenize=False, add_generation_prompt=True, **self._template_kwargs())
        metadata = VideoMetadata(total_num_frames=len(frames), fps=self.sampling_fps,
                                 frames_indices=list(range(len(frames))))
        original = self.processor._calculate_timestamps
        def pts_timestamps(processor, indices, fps, merge_size=2):
            if list(indices) != list(range(len(frames))) or merge_size != timing['temporal_patch_size']:
                raise ValueError('Processor changed frozen frame ordering')
            return [g['timestamp_s'] for g in timing['groups']]
        self.processor._calculate_timestamps = types.MethodType(pts_timestamps, self.processor)
        try:
            inputs = self.processor(text=[text], videos=[resized], video_metadata=[metadata],
                    do_sample_frames=False, do_resize=False, cap_pixels_per_frame=False,
                    input_data_format='channels_first', return_tensors='pt')
        finally:
            self.processor._calculate_timestamps = original
        inputs.pop('video_metadata', None)
        grid = inputs['video_grid_thw'].tolist()
        if len(grid) != 1 or int(grid[0][0]) != len(timing['groups']):
            raise ValueError('Video frame grouping changed')
        actual = [int(grid[0][2]) * vp.patch_size, int(grid[0][1]) * vp.patch_size]
        if actual != target:
            raise ValueError('Video processor changed image-matched dimensions')
        decoded = self.processor.tokenizer.decode(inputs['input_ids'][0], skip_special_tokens=False)
        encoded_times = [float(t) for t in re.findall(r'<([0-9]+\.[0-9]+) seconds>', decoded)]
        if encoded_times != [g['display_timestamp_s'] for g in timing['groups']]:
            raise ValueError('Encoded timestamps do not match true PTS groups')
        import hashlib
        self.rendered_template = text
        self.prepared_metadata = {'template_summary':{'pre_expansion_sha256':hashlib.sha256(text.encode()).hexdigest(), 'template_kwargs':self._template_kwargs(), 'has_system_message':text.startswith('<|im_start|>system'), 'effective_reasoning_effort':(self.reasoning_effort or 'xhigh') if self.thinking else None}, 'input_mode': 'video', 'image_sizes': [actual] * len(frames),
                'video_grid_thw': grid, 'temporal_evidence': timing,
                'encoded_timestamps_s': encoded_times, 'do_sample_frames': False, 'do_resize': False}
        return inputs

    def prepare(self, prompt, frames, times, folder, expected_sizes=None):
        self.prepared_metadata = {}
        inputs = (self._video_inputs(prompt, frames, times) if self.input_mode == 'video'
                  else self._inputs(prompt, frames, times))
        patch = self.processor.image_processor.patch_size
        sizes = (self.prepared_metadata['image_sizes'] if self.input_mode == 'video' else
                 [[int(g[2]) * patch, int(g[1]) * patch] for g in inputs['image_grid_thw'].tolist()])
        if expected_sizes is not None and sizes != expected_sizes:
            raise ValueError('Processed sizes differ from frozen baseline')
        path = Path(folder) / 'inputs.pt'
        self.torch.save(dict(inputs), path)
        if self.input_mode == 'video':
            (Path(folder)/'rendered_template.txt').write_text(self.rendered_template)
        return {'path': str(path), 'sha256': sha(path), 'image_count': len(frames),
                'input_mode': self.input_mode, 'thinking_enabled': self.thinking, 'image_sizes': sizes,
                **self.prepared_metadata, 'request_bytes': path.stat().st_size,
                'estimated_usage': {'input_tokens': inputs['input_ids'].shape[1]},
                'estimate_note': 'Actual locally prepared input tokens; no GPU generation'}

    def prepare_text(self, prompt, folder):
        inputs = self.processor.apply_chat_template([{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}], tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors='pt', **self._template_kwargs())
        path = Path(folder) / 'summary_inputs.pt'
        self.torch.save(dict(inputs), path)
        return {'path': str(path), 'sha256': sha(path), 'request_bytes': path.stat().st_size,
                'estimated_usage': {'input_tokens': inputs['input_ids'].shape[1]}}

    def artifacts_valid(self, bundle):
        r = bundle.get('request')
        return bool(r and Path(r['path']).is_file() and sha(r['path']) == r['sha256'])

    def generate_prepared(self, request):
        if sha(request['path']) != request['sha256']:
            raise ValueError('Prepared tensor inputs changed')
        self.current_task_id = request.get('task_id')
        if self.sampling and not self.current_task_id:
            raise ValueError('Sampling requires stable task identity')
        self._load()
        inputs = self.torch.load(request['path'], map_location='cpu', weights_only=True)
        text, detail = self._generate({k: v.to(self.model.device) for k, v in inputs.items()})
        detail.update({k: request[k] for k in ('input_mode', 'image_sizes', 'temporal_evidence', 'video_grid_thw', 'encoded_timestamps_s') if k in request})
        detail['processed_sizes'] = request.get('image_sizes', detail['processed_sizes'])
        if 'token_trace' in detail:
            from caption_system.results.atomic import atomic_json
            trace_path = Path(request['path']).parent / 'generation_trace.json'
            atomic_json(trace_path, detail.pop('token_trace'))
            detail['generation_trace_path'] = str(trace_path)
        return text, detail

    def generate(self, prompt, frames, times):
        self._load()
        return self._generate(self._inputs(prompt, frames, times).to(self.model.device))

    def _generate(self, inputs):
        sampling = getattr(self, 'sampling', None)
        decode = {'do_sample':False}
        chosen_seed = None
        if sampling:
            from caption_system.models.sampling import task_seed
            chosen_seed = task_seed(sampling['base_seed'], self.current_task_id)
            self.torch.manual_seed(chosen_seed)
            decode = {k:sampling[k] for k in ('do_sample','temperature','top_p','top_k','min_p','repetition_penalty')}
        self.torch.cuda.synchronize()
        start = time.perf_counter()
        for i in range(self.torch.cuda.device_count()):
            self.torch.cuda.reset_peak_memory_stats(i)
        trace = None
        kwargs = {}
        if self.trace_tokens:
            from caption_system.models.token_trace import TokenTrace
            from transformers.generation.stopping_criteria import StoppingCriteria, StoppingCriteriaList
            closing = self.processor.tokenizer.encode('</think>', add_special_tokens=False)
            eos = self.model.generation_config.eos_token_id
            trace = TokenTrace(self.thinking, closing, eos if isinstance(eos,list) else [eos])
            prompt_tokens = inputs['input_ids'].shape[1]
            class CaptionBudget(StoppingCriteria):
                def __call__(criterion, ids, scores, **unused):
                    position = trace.close_position if self.thinking else 0
                    return position is not None and ids.shape[1] - prompt_tokens - position >= self.caption_max_tokens
            kwargs['streamer'] = trace
            if self.caption_max_tokens:
                kwargs['stopping_criteria'] = StoppingCriteriaList([CaptionBudget()])
        if sampling and sampling['presence_penalty']:
            from caption_system.models.sampling import GeneratedPresencePenalty
            from transformers.generation.logits_process import LogitsProcessorList
            kwargs['logits_processor'] = LogitsProcessorList([GeneratedPresencePenalty(inputs['input_ids'].shape[1], sampling['presence_penalty'])])
        with self.torch.inference_mode():
            tokens = self.model.generate(**inputs, max_new_tokens=self.max_tokens, **decode, **kwargs)
        self.torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        text = self.processor.batch_decode(tokens[:, inputs['input_ids'].shape[1]:], skip_special_tokens=True)[0].strip()
        patch = self.processor.image_processor.patch_size
        generated = tokens.shape[1] - inputs['input_ids'].shape[1]
        trace_detail = {}
        if trace:
            generated_ids = tokens[0, inputs['input_ids'].shape[1]:].tolist()
            trace_detail = trace.metrics(start, start + elapsed, generated_ids)
            trace_detail['token_trace'] = {'generated_token_ids':trace.ids,'relative_token_times_s':[t-start for t in trace.times],
                                         'thought_end_position':trace.close_position,'metrics':{k:v for k,v in trace_detail.items()}}
        return (text, {**trace_detail, **({'effective_sampling':sampling,'task_seed':chosen_seed,'reasoning_effort':self.reasoning_effort if self.thinking else None} if sampling else {}), 'generation_seconds': elapsed, 'input_tokens': inputs['input_ids'].shape[1], 'generated_tokens': generated,
                       'reported_model': type(self.model).__name__,
                       'peak_gpu_allocated_bytes': {str(i): self.torch.cuda.max_memory_allocated(i) for i in range(self.torch.cuda.device_count())},
                       'peak_gpu_reserved_bytes': {str(i): self.torch.cuda.max_memory_reserved(i) for i in range(self.torch.cuda.device_count())},
                       'finish_reason': ('stop' if trace_detail.get('caption_complete') else 'length') if trace else ('length' if generated >= self.max_tokens else 'stop'),
                       'processed_sizes': [[int(g[2]) * patch, int(g[1]) * patch] for g in inputs.get('image_grid_thw', self.torch.empty((0,3))).tolist()]})
