"""Explicit audited syntax-only normalization; no model calls or caption rewriting."""
import argparse,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from caption_system.results.store import RunStore,sha
from caption_system.results.contract import validate
from caption_system.data.tasks import read_jsonl

def trailing_quote_object(raw):
    text=raw.split('</think>')[-1].strip()
    if text.startswith('```'):text=text.split('\n',1)[1].rsplit('```',1)[0].strip()
    value,end=json.JSONDecoder().raw_decode(text)
    if not isinstance(value,dict) or text[end:].strip()!='"':
        raise ValueError('Not exactly one complete JSON object followed by one stray quote')
    return value

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
    folder=PROJECT/'runs'/a.run
    parent=RunStore(a.run,json.loads((folder/'config.json').read_text()),read_jsonl(folder/'tasks.jsonl'))
    count=0
    try:
        for directory in sorted((folder/'windows').glob('*')):
            if not (directory/'config.json').exists():continue
            rows=read_jsonl(directory/'tasks.jsonl');lookup={r['task_id']:r for r in rows}
            store=RunStore(directory.name,json.loads((directory/'config.json').read_text()),rows,root=folder/'windows')
            try:
                for old in list(store.records.values()):
                    if old.get('caption_status')!='failed' or old.get('output_status')!='parse_failed':continue
                    try:
                        value=trailing_quote_object(old.get('raw_model_output',''));task=lookup[old['task_id']]
                        annotation=validate(value,task['clip_end_time_s']-task['clip_start_time_s'],old.get('sampled_times_s',[]))
                    except (ValueError,KeyError,TypeError):print(old['task_id'],'not_normalizable');continue
                    count+=1;print(old['task_id'],'trailing_quote_only','apply' if a.apply else 'plan')
                    if a.apply:
                        record={k:v for k,v in old.items() if k not in ('result_id','attempt_id','error')}
                        record.update(caption_status='success',output_status='valid_normalized',generated_caption=annotation['generated_caption'],annotation=annotation,normalization={'type':'trailing_quote_only','source_result_id':old['result_id'],'script_sha256':sha(__file__),'model_calls':0})
                        store.save(record);store.event('syntax_normalization',task_id=old['task_id'],source_result_id=old['result_id'],script_sha256=sha(__file__))
            finally:store.close()
        parent.event('window_normalization',apply=a.apply,candidates=count,model_calls=0)
    finally:parent.close()
    print('Candidates',count,'model calls 0; original versions retained')
if __name__=='__main__':main()
