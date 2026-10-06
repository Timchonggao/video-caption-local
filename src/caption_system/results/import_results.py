"""Validate and idempotently import external task results into a local run."""
import argparse, json
from pathlib import Path
from caption_system.config import PROJECT, VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.store import RunStore, validate_result

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--run', required=True)
    p.add_argument('--model-key', choices=['qwen', 'doubao', 'gemini'], required=True)
    p.add_argument('--model-name', required=True)
    p.add_argument('--prompt-id', required=True)
    a = p.parse_args()
    tasks = read_jsonl(PROJECT / 'metadata/tasks.jsonl')
    lookup = {t['task_id']: t for t in tasks}
    records = read_jsonl(a.input)
    seen = set()
    for r in records:
        validate_result(r, lookup)
        if r['task_id'] in seen:
            raise ValueError('Duplicate imported task')
        seen.add(r['task_id'])
    labels = json.loads((PROJECT / 'configs/models.json').read_text())
    store = RunStore(a.run, {'version': VERSION, 'provider': 'external', 'model_key': a.model_key, 'model_name': a.model_name, 'model_label': labels[a.model_key]['label'], 'prompt_id': a.prompt_id}, tasks)
    try:
        for r in records:
            existing = store.records.get(r['task_id'])
            if existing:
                if {k: v for k, v in existing.items() if k != 'run_id'} != {k: v for k, v in r.items() if k != 'run_id'}:
                    raise ValueError('Existing result differs; use a new run ID')
        for r in records:
            if r['task_id'] not in store.records:
                store.save(r)
    finally:
        store.close()
    print(f'Imported {len(records)} records')
if __name__ == '__main__':
    main()
