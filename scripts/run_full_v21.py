"""Frozen 2 fps whole-subsegment release: pilot first, then resumable six-group run."""
import argparse,collections,json,os,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from caption_system.data.tasks import read_jsonl
from caption_system.pipeline.context import ordered
from caption_system.config import PATHS


def manifest():
    tasks=ordered([t for t in read_jsonl(PROJECT/'metadata/tasks.jsonl') if t['camera_id']=='camera2'])
    samples=collections.defaultdict(list)
    for t in tasks:samples[t['sample_id']].append(t)
    first=[min(rows,key=lambda t:(t['clip_start_time_s'],t['clip_end_time_s'],t['task_id']))['task_id'] for _,rows in sorted(samples.items())]
    if len(tasks)!=138 or len(first)!=10:raise ValueError('Unexpected dataset scope')
    return tasks,first


def command(c,provider,mode,pilot=False,apply=False):
    tasks,first=manifest();scope=[t['task_id'] for t in tasks] if mode=='off' else first
    rid=c['runs'][provider][mode]
    cmd=[sys.executable,str(PROJECT/('scripts/caption_api_paced.py' if provider=='doubao' else 'scripts/caption.py')),'--run',rid,'--provider',provider,
         '--camera','camera2','--input-mode','video','--sampling-fps','2','--release-id','v2_1',
         '--prompt-id',c['prompt_id'],'--prompt',str(PROJECT/c['prompt_file']),'--background','none',
         '--artifact-root',str(Path(PATHS['cache_root'])/'v2_1/artifacts'),
         '--limit',str(len(scope)),'--max-calls',str(len(scope)),'--stop-on-error']
    for tid in scope:cmd.extend(['--experiment-task-id',tid])
    if provider=='qwen':
        off=mode=='off'
        cmd.extend(['--frame-max-pixels','512000','--max-new-tokens','4096','--caption-max-tokens','512',
                    '--max-request-bytes',str(2*2**30),'--trace-tokens','--do-sample','--no-preserve-thinking',
                    '--top-k','20','--min-p','0','--repetition-penalty','1','--base-seed','20261006',
                    '--seed-index','1','--official-profile',mode,'--temperature','.7' if off else '1',
                    '--top-p','.8' if off else '.95','--presence-penalty','1.5' if off else '0'])
        if not off:cmd.extend(['--thinking','--reasoning-effort',mode])
    else:
        cmd.extend(['--model',c['doubao_model'],'--max-new-tokens','512' if mode=='off' else '4096',
                    '--max-request-bytes','63000000','--video-transport','auto',
                    '--video-cache-root',str(Path(PATHS['cache_root'])/'v2_1/doubao_exports'),
                    '--doubao-thinking','disabled' if mode=='off' else 'enabled'])
    if pilot:
        cmd.extend(['--task-id',first[0]])
        if mode=='off':cmd.extend(['--task-id',max(tasks,key=lambda t:t['clip_end_time_s']-t['clip_start_time_s'])['task_id']])
    if apply:cmd.append('--apply')
    return cmd


def verify(c,provider,mode,pilot=False):
    tasks,first=manifest();folder=PROJECT/'runs'/c['runs'][provider][mode]
    ids=([first[0]]+([max(tasks,key=lambda t:t['clip_end_time_s']-t['clip_start_time_s'])['task_id']] if mode=='off' else [])) if pilot else ([t['task_id'] for t in tasks] if mode=='off' else first)
    active=json.loads((folder/'active.json').read_text())['selection']
    failures=[]
    for tid in ids:
        row=json.loads((folder/'versions'/(active[tid]+'.json')).read_text()) if tid in active else {}
        if row.get('caption_status')!='success' or row.get('finish_reason')!='stop' or not row.get('caption_complete'):
            failures.append({'task':tid,'status':row.get('caption_status','missing'),'error':row.get('error')})
    if failures:raise RuntimeError(json.dumps({'run':folder.name,'failures':failures},ensure_ascii=False))
    if provider=='qwen' and mode!='off':
        source=PROJECT/'runs'/c['runs']['qwen']['off'];index=json.loads((source/'active.json').read_text())['selection']
        for tid in ids:
            record=json.loads((folder/'versions'/(active[tid]+'.json')).read_text());reference=json.loads((source/'versions'/(index[tid]+'.json')).read_text())
            a=json.loads((folder/'inputs'/(record['input_id']+'.json')).read_text());b=json.loads((source/'inputs'/(reference['input_id']+'.json')).read_text())
            if [(x['pts'],x['sha256']) for x in a['frames']]!=[(x['pts'],x['sha256']) for x in b['frames']]:raise ValueError('First-task visual evidence differs across thinking modes')
    return len(ids)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['plan','pilot','full','all'],default='plan')
    parser.add_argument('--provider',choices=['qwen','doubao','all'],default='all')
    parser.add_argument('--mode',choices=['off','low','medium','xhigh','on'],help='Run one independent group, allowing explicit process-level parallelism')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();c=json.loads((PROJECT/'configs/full_v21.json').read_text());tasks,first=manifest()
    print('v2.1: 138 camera2 clips, Qwen 168 + Doubao 148 = 316 records. No windows/background/history.',flush=True)
    if args.phase=='plan':return
    if args.phase=='all' and not args.apply:parser.error('--phase all requires --apply')
    env=dict(os.environ);env['OMP_NUM_THREADS']=env['MKL_NUM_THREADS']='4'
    providers=['qwen','doubao'] if args.provider=='all' else [args.provider]
    if 'doubao' in providers and args.apply and (not env.get('ARK_API_KEY') or env.get('ARK_MODEL')!=c['doubao_model']):raise ValueError('Load configured Ark credentials; no keys are printed')
    phases=['pilot','full'] if args.phase=='all' else [args.phase]
    for phase in phases:
        for provider in providers:
            modes=[args.mode] if args.mode else list(c['runs'][provider])
            if any(mode not in c['runs'][provider] for mode in modes):parser.error('Mode not valid for selected provider')
            for mode in modes:
                if phase=='full' and args.apply:verify(c,provider,mode,pilot=True)
                print('Running',provider,mode,phase,flush=True)
                subprocess.run(command(c,provider,mode,pilot=phase=='pilot',apply=args.apply),env=env,cwd=PROJECT,check=True)
                if args.apply:print('Verified',provider,mode,verify(c,provider,mode,pilot=phase=='pilot'),flush=True)
    print('Requested phase complete.',flush=True)

if __name__=='__main__':main()
