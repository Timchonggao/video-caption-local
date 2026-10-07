"""One in-flight preparation/call initially, with no implicit paid retries."""
import json
import time
from caption_system.pipeline.prepare import prepare
from caption_system.results.contract import validate
from caption_system.results.atomic import atomic_json

def execute(store, rows, predecessors, config, backend, prompt, options):
    hashes, previews = {}, []
    calls, handled = 0, 0
    for task in rows:
        if options.limit and handled >= options.limit:
            break
        tid = task['task_id']
        old = store.records.get(tid, {})
        if options.apply and store.uncertain(tid) and not options.retry_unknown:
            print(tid, 'blocked_unknown_remote_outcome', flush=True)
            continue
        if options.apply and not options.rerun and (config.get('experiment_family') == 'official-qwen38-v2' or config.get('release_id') == 'v2_1') and old.get('caption_status') == 'failed':
            print(tid,'retained_failed_no_retry',flush=True)
            continue
        record = {k: task[k] for k in ('task_id', 'clip_id', 'sample_id', 'camera_id')}
        record.update(caption_status='failed', generated_caption='', execution_status='preparation_failed', output_status='not_produced', quality_status='unreviewed')
        start = time.perf_counter()
        try:
            bundle = prepare(store, task, predecessors[tid], config, backend, prompt, hashes)
            previews.append({'task_id': tid, 'input_id': bundle['input_id'], 'ready': bundle['ready'],
                             'context_final': bundle['context_final'],
                             'path': f"inputs/{bundle['input_id']}.json", 'request': bundle.get('request')})
            if not options.apply or not bundle['ready']:
                handled += 1
                print(tid, 'prepared' if bundle['ready'] else 'waiting_for_context', flush=True)
                continue
            if not options.rerun and old.get('caption_status') == 'success':
                status = 'reused' if old.get('input_fingerprint') == bundle['input_fingerprint'] and not old.get('context_changed') else 'input_changed_requires_explicit_rerun'
                print(tid, status, flush=True)
                continue
            if calls >= options.max_calls:
                break
            if options.retry_unknown and store.uncertain(tid):
                store.acknowledge_unknown(tid)
            attempt = store.begin(tid, bundle['input_id'], remote=config['provider'] != 'qwen')
            record.update(attempt_id=attempt, input_id=bundle['input_id'], input_fingerprint=bundle['input_fingerprint'],
                          parent_result_id=bundle['context']['history']['result_id'], context=bundle['context'],
                          sampled_times_s=[m['relative_time_s'] for m in bundle['frames']],
                          source_interval_s=bundle['source_interval_s'], video_sha256=bundle['video_sha256'])
            record['execution_status'] = 'request_failed'
            calls += 1
            raw, extra = backend.generate_prepared(bundle['request'])
            record.update(extra, raw_model_output=raw, execution_status='returned')
            if extra.get('finish_reason') in ('length', 'MAX_TOKENS'):
                record['output_status'] = 'truncated'
                raise ValueError('Output truncated; response retained')
            if config.get('thinking') is True and (not extra.get('thinking_complete') or not extra.get('caption_complete')):
                record['output_status'] = 'missing_final_caption'
                raise ValueError('Thinking/final caption did not complete; raw output retained')
            answer = raw.split('</think>')[-1].strip()
            if answer.startswith('```'):
                answer = answer.split('\n', 1)[1].rsplit('```', 1)[0].strip()
            record['output_status'] = 'parse_failed'
            value = json.loads(answer) if config['structured'] else {'generated_caption': answer}
            record['output_status'] = 'schema_failed'
            detail = validate(value, task['clip_end_time_s'] - task['clip_start_time_s'], record['sampled_times_s']) if config['structured'] else value
            if not detail['generated_caption'].strip():
                raise ValueError('Empty caption')
            record.update(caption_status='success', output_status='valid', generated_caption=detail['generated_caption'], annotation=detail)
        except Exception as error:
            record.update(getattr(error, 'result_metadata', {}))
            record.update(error=type(error).__name__ + ': ' + str(error))
            record['execution_status'] = getattr(error, 'execution_status', record['execution_status'])
            if not options.apply:
                previews.append({'task_id': tid, 'ready': False, 'error': record['error']})
                store.event('preview_failed', task_id=tid, error=record['error'])
                handled += 1
                continue
        record['elapsed_seconds'] = time.perf_counter() - start
        store.save(record)
        handled += 1
        print(tid, record['caption_status'], record['output_status'], flush=True)
        if record['caption_status'] == 'failed' and getattr(options, 'stop_on_error', False):
            if not (getattr(options,'continue_incomplete',False) and record['output_status'] in ('truncated','missing_final_caption')):
                break
    atomic_json(store.root / 'preview.json', {'model_called': bool(calls), 'calls_this_invocation': calls, 'inputs': previews})
    from caption_system.pipeline.preview import write_preview
    write_preview(store.root, previews)
