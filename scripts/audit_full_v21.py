"""Check release identities, actual sampling intervals and provider request settings."""
import argparse,hashlib,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/'scripts'))
sys.path.insert(0,str(PROJECT/'src'))
from run_full_v21 import manifest
from caption_system.results.artifacts import resolve_artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--require-complete',action='store_true');args=parser.parse_args()
    config=json.loads((PROJECT/'configs/full_v21.json').read_text());tasks,first=manifest();lookup={t['task_id']:t for t in tasks};checked=[];evidence={};exports={};gaps=[]
    for provider,runs in config['runs'].items():
        for mode,rid in runs.items():
            folder=PROJECT/'runs'/rid
            if not (folder/'config.json').is_file():continue
            frozen=json.loads((folder/'config.json').read_text())
            assert frozen['sampling_fps']==2 and frozen['background']=='none' and not frozen['contextual'] and not frozen.get('window_seconds')
            assert frozen['camera']=='camera2' and frozen['release_id']=='v2_1'
            ids=json.loads((folder/'active.json').read_text())['selection'] if (folder/'active.json').is_file() else {}
            scope=set(lookup if mode=='off' else first);assert set(ids)<=scope
            for tid in sorted(scope-set(ids)):
                gaps.append({'run_id':rid,'task_id':tid,'status':'pending'})
            for tid,result_id in ids.items():
                r=json.loads((folder/'versions'/(result_id+'.json')).read_text())
                assert r['task_id']==tid and r['result_id']==result_id and r['run_id']==rid
                if r['caption_status']!='success':
                    gaps.append({'run_id':rid,'task_id':tid,'status':r['caption_status'],'error':r.get('error')})
                    continue
                assert r['finish_reason']=='stop' and r['caption_complete']
                b=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text());task=lookup[tid]
                assert b['source_interval_s']==[task['clip_start_time_s'],task['clip_end_time_s']] and b['context']['history']['status']=='disabled'
                if provider=='qwen':
                    frames=b['frames'];assert frames and b['request']['do_sample_frames'] is False
                    sizes=b['request']['image_sizes']
                    assert len(sizes)==len(frames)==len(r['processed_sizes'])
                    assert sizes==r['processed_sizes']
                    assert all(len(size)==2 and 0<size[0]*size[1]<=512000 for size in sizes)
                    times=[f['source_time_s'] for f in frames]
                    assert all(task['clip_start_time_s']<=t<task['clip_end_time_s'] for t in times)
                    assert all(a<b for a,b in zip(times,times[1:]));assert all(abs(f['deviation_s'])<=1 for f in frames)
                    assert b['request']['temporal_evidence']['real_frame_count']==len(frames)
                    assert b['request']['temporal_evidence']['encoded_frame_count']==len(frames)+b['request']['temporal_evidence']['padding_count']
                    assert b['request']['encoded_timestamps_s']==r['encoded_timestamps_s']
                    for frame in frames:
                        image=resolve_artifact(folder,frame['path'])
                        assert image.is_file() and hashlib.sha256(image.read_bytes()).hexdigest()==frame['sha256']
                    signature=[(f['pts'],f['sha256']) for f in frames]
                    if tid in evidence:assert evidence[tid]==signature
                    evidence[tid]=signature
                    assert r['task_seed'] is not None and r['effective_sampling']['base_seed']==20261006
                else:
                    request=b['request'];body=json.loads(Path(request['path']).read_text());assert body['thinking']=={'type':'disabled' if mode=='off' else 'enabled'}
                    assert body['max_tokens']==(512 if mode=='off' else 4096)
                    assert not any(k in body for k in ['temperature','top_p','min_frame_tokens','max_frame_tokens','max_video_tokens'])
                    assert r['provider_transport']==request['transport'] and r['provider_sampling_known'] is False
                    if request['transport']=='files':assert request['file_preprocess_configs']=={'video':{'fps':2}}
                    else:assert body['messages'][0]['content'][1]['video_url']['fps']==2 and request['request_bytes']<63_000_000
                    digest=request['video_artifact']['sha256']
                    if tid in exports:assert exports[tid]==digest
                    exports[tid]=digest
                checked.append({'run_id':rid,'task_id':tid,'result_id':result_id})
    complete=len(checked)==316 and not gaps
    out=PROJECT/'reports/experiments/v2_1/input-audit.json';out.write_text(json.dumps({'checked':len(checked),'expected':316,'complete':complete,'gaps':gaps,'identities':checked,'qwen_unique_task_evidence':len(evidence),'doubao_unique_video_exports':len(exports)},ensure_ascii=False,indent=2)+'\n')
    print('Input/identity audit:',len(checked),'/316; gaps:',len(gaps))
    if args.require_complete and not complete:raise SystemExit('Release not complete')

if __name__=='__main__':main()
