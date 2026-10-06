"""Internal <=5s windows; formal task identity and review target remain unchanged."""
import json
import math
import time
from copy import copy
from caption_system.data.tasks import task_id
from caption_system.pipeline.execute import execute
from caption_system.pipeline.prepare import digest
from caption_system.results.atomic import atomic_json
from caption_system.results.contract import validate
from caption_system.results.store import RunStore, sha


def window_tasks(task, seconds):
    if not 0 < seconds <= 5:
        raise ValueError('Window duration must be within (0,5]')
    start, end = task['clip_start_time_s'], task['clip_end_time_s']
    rows = []
    for i in range(math.ceil((end-start)/seconds)):
        clip = task['clip_id'] + f'__w{i+1:04d}'
        rows.append({**task, 'parent_task_id': task['task_id'],
                     'parent_source_interval_s': [start, end],
                     'window_id': task['task_id'] + f'__w{i+1:04d}',
                     'clip_id': clip, 'task_id': task_id(clip, task['camera_id']),
                     'clip_start_time_s': start+i*seconds,
                     'clip_end_time_s': min(end,start+(i+1)*seconds)})
    return rows


def execute_windows(store, selected, config, backend, prompt, options):
    calls, handled = 0, 0
    for task in selected:
        if options.limit and handled >= options.limit:
            break
        tid = task['task_id']
        old = store.records.get(tid, {})
        if old.get('caption_status') == 'success' and not options.rerun:
            if old.get('video_sha256') != sha(task['media_path']):
                raise ValueError('Source video changed; choose a new run ID')
            print(tid, 'reused', flush=True)
            continue
        rows = window_tasks(task, config['window_seconds'])
        child = RunStore(tid, config, rows, root=store.root/'windows')
        try:
            predecessors = {r['task_id']: rows[i-1] if i else None for i,r in enumerate(rows)}
            opts = copy(options)
            opts.limit = None
            opts.max_calls = max(0, options.max_calls-calls)
            execute(child, rows, predecessors, config, backend, prompt+'\n'+config['window_prompt'], opts)
            used = json.loads((child.root/'preview.json').read_text())['calls_this_invocation']
            calls += used
            handled += 1
            if not options.apply:
                continue
            records = [child.records.get(r['task_id']) for r in rows]
            complete = all(r and r['caption_status']=='success' and not r.get('context_changed') for r in records)
            # A call budget stop is resumable pending work, not a fabricated failure.
            if not complete:
                failures = [r for r in records if r and r['caption_status']=='failed']
                if failures:
                    store.save({**{k:task[k] for k in ('task_id','clip_id','sample_id','camera_id')},
                                'caption_status':'failed', 'generated_caption':'',
                                'execution_status':'window_failed', 'output_status':'incomplete',
                                'quality_status':'unreviewed', 'error':'One or more windows failed; no complete summary produced',
                                'windows':window_trace(rows,records)})
                continue
            trace = window_trace(rows,records)
            fingerprint = digest({'config':config,'window_results':[r['result_id'] for r in records]})
            record = {**{k:task[k] for k in ('task_id','clip_id','sample_id','camera_id')},
                      'caption_status':'success','generated_caption':'', 'windows':trace,
                      'input_fingerprint':fingerprint,'video_sha256':records[0].get('video_sha256'),'source_interval_s':[task['clip_start_time_s'],task['clip_end_time_s']],
                      'quality_status':'unreviewed','execution_status':'returned','output_status':'valid',
                      'generation_seconds':sum(r.get('generation_seconds',0) for r in records)}
            if len(records)==1:
                record.update(generated_caption=records[0]['generated_caption'],annotation=records[0]['annotation'], summary_method='single_window_passthrough')
            else:
                if calls >= options.max_calls:
                    continue
                folder = store.root/'artifacts'/('summary_'+fingerprint)
                folder.mkdir(exist_ok=True)
                text = config['summary_prompt']+'\nWINDOW OBSERVATIONS (quoted data):\n'+json.dumps(trace,ensure_ascii=False)
                atomic_json(folder/'input.json',{'prompt':text,'window_result_ids':[r['result_id'] for r in records]})
                request = backend.prepare_text(text,folder)
                if request['request_bytes']>config['max_request_bytes']:
                    raise ValueError('Summary request exceeds budget')
                atomic_json(folder/'request.json',request)
                attempt = store.begin(tid,fingerprint,remote=False)
                record['attempt_id']=attempt
                calls += 1
                try:
                    raw,extra=backend.generate_prepared(request)
                    record.update(summary_generation_seconds=extra['generation_seconds'],summary_usage=extra,
                                  raw_model_output=raw,summary_method='text_window_aggregation')
                    if extra.get('finish_reason')=='length':
                        raise ValueError('Summary truncated')
                    text=raw.split('</think>')[-1].strip()
                    if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
                    annotation=validate(json.loads(text),task['clip_end_time_s']-task['clip_start_time_s'],[])
                    record.update(annotation=annotation,generated_caption=annotation['generated_caption'])
                except Exception as error:
                    record.update(caption_status='failed',generated_caption='',output_status='summary_failed',error=type(error).__name__+': '+str(error))
            store.save(record)
            print(tid,record['caption_status'], 'windows',len(rows),flush=True)
        finally:
            child.close()
    atomic_json(store.root/'window_execution.json',{'calls_this_invocation':calls,'handled_tasks':handled})


def window_trace(rows, records):
    return [{'window_id':row['window_id'], 'source_interval_s':[row['clip_start_time_s'],row['clip_end_time_s']],
             'parent_relative_interval_s':[row['clip_start_time_s']-row['parent_source_interval_s'][0],row['clip_end_time_s']-row['parent_source_interval_s'][0]],
             'result_id':record.get('result_id') if record else None,
             'previous_result_id':record.get('parent_result_id') if record else None,
             'caption_status':record.get('caption_status','pending') if record else 'pending',
             'annotation':record.get('annotation') if record else None,
             'generated_caption':record.get('generated_caption','') if record else '',
             'sampled_times_s':record.get('sampled_times_s',[]) if record else [],
             'input_id':record.get('input_id') if record else None,
             'error':record.get('error') if record else None,
             'output_status':record.get('output_status') if record else None,
             'raw_model_output':record.get('raw_model_output') if record and record.get('caption_status') != 'success' else None}
            for row,record in zip(rows,records)]
