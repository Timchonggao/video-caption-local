"""Completed official retest. Plan is read-only; generation is retired.

The current config retains four profiles with base seed 20261006.
Use a new run ID for future experiments; never recreate removed runs.
"""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
PILOT=['sample_01_seg02_sub10__camera2','sample_01_seg02_sub12__camera2']

def run_id(profile,index):return f'qwen-sample01-v2-official-{profile}-s{index}'

def command(c,profile,index,pilot=False,apply=False):
    params=c['profiles'][profile];seed=c['seeds'][index-1]
    cmd=[sys.executable,str(PROJECT/'scripts/caption.py'),'--run',run_id(profile,index),'--provider','qwen','--sample',c['sample'],'--camera',c['camera'],
        '--input-mode','video','--sampling-fps',str(c['sampling_fps']),'--frame-max-pixels',str(c['frame_max_pixels']),
        '--evidence-run',c['evidence_run'],'--prompt-id','baseline-v2','--prompt',str(PROJECT/c['prompt_file']),'--background','none',
        '--max-new-tokens',str(c['max_new_tokens']),'--caption-max-tokens',str(c['caption_max_tokens']),
        '--max-request-bytes',str(c['max_request_bytes']),'--trace-tokens','--do-sample','--no-preserve-thinking',
        '--top-k','20','--min-p','0','--repetition-penalty','1','--base-seed',str(seed),'--seed-index',str(index),
        '--official-profile',profile,'--limit','5','--max-calls','5','--stop-on-error','--continue-incomplete']
    for key in ['temperature','top_p','presence_penalty']:cmd.extend(['--'+key.replace('_','-'),str(params[key])])
    if params['thinking']:cmd.extend(['--thinking','--reasoning-effort',profile])
    for task in c['task_ids']:cmd.extend(['--experiment-task-id',task])
    if pilot:
        for task in PILOT:cmd.extend(['--task-id',task])
    if apply:cmd.append('--apply')
    return cmd


def verify(c,profile,index,expected):
    folder=PROJECT/'runs'/run_id(profile,index);active=json.loads((folder/'active.json').read_text())['selection']
    for task in expected:
        if task not in active:raise ValueError('Missing result after phase; possible technical error')
        r=json.loads((folder/'versions'/(active[task]+'.json')).read_text())
        if r['caption_status']=='failed' and r['output_status'] not in ['truncated','missing_final_caption']:
            raise ValueError(f'Technical failure: {profile}/{task}: '+r.get('error',''))
        if r['caption_status']=='success' and (not r.get('caption_complete') or not r.get('thinking_complete')):
            raise ValueError('Incomplete output incorrectly marked successful')
        if r.get('effective_sampling',{}).get('base_seed')!=c['seeds'][index-1]:raise ValueError('Sampling metadata missing')
        sys.path.insert(0,str(PROJECT/'src'))
        from caption_system.models.sampling import task_seed
        if r.get('task_seed') != task_seed(c['seeds'][index-1],task):raise ValueError('Derived task seed differs')
    attempts=len(list((folder/'attempts').glob('*.json')))
    if attempts>5:raise ValueError('Unexpected duplicate attempts')


def prepare(c,env):
    import torch
    torch.set_num_threads(c['cpu_threads'])
    baseline=PROJECT/'runs'/c['evidence_run']
    active=json.loads((baseline/'active.json').read_text())['selection']
    if shutil.disk_usage(PROJECT).free<20*2**30:raise RuntimeError('Need at least 20 GiB free before CPU preparation')
    for index in range(1,len(c['seeds'])+1):
        for profile in c['profiles']:
            subprocess.run(command(c,profile,index),env=env,cwd=PROJECT,check=True)
            folder=PROJECT/'runs'/run_id(profile,index);preview=json.loads((folder/'preview.json').read_text())
            if len(preview['inputs'])!=5 or not all(x.get('ready') for x in preview['inputs']):raise ValueError('CPU preparation failed')
            for item in preview['inputs']:
                b=json.loads((folder/item['path']).read_text());summary=b['request']['template_summary'];kw=summary['template_kwargs']
                if kw.get('preserve_thinking') is not False or kw.get('enable_thinking')!=c['profiles'][profile]['thinking']:raise ValueError('Template flags not applied')
                if profile!='off' and summary['effective_reasoning_effort']!=profile:raise ValueError('Wrong effective effort')
                record=json.loads((baseline/'versions'/(active[b['task_id']]+'.json')).read_text())
                original=json.loads((baseline/'inputs'/(record['input_id']+'.json')).read_text())
                if b['prompt']!=original['prompt'] or [(f['pts'],f['sha256']) for f in b['frames']]!=[(f['pts'],f['sha256']) for f in original['frames']]:raise ValueError('Frozen prompt or frames differ')
                if b['request']['temporal_evidence']!=original['request']['temporal_evidence']:raise ValueError('PTS mapping changed')
                source=torch.load(original['request']['path'],map_location='cpu',weights_only=True)
                prepared=torch.load(b['request']['path'],map_location='cpu',weights_only=True)
                torch.testing.assert_close(source['pixel_values_videos'],prepared['pixel_values_videos'],rtol=0,atol=0)
                del source,prepared
            print(profile,index,'CPU inputs verified',flush=True)


def phase(c,env,name):
    index=2 if name=='seed2' else 1
    for profile in c['profiles']:
        if name=='seed1':verify(c,profile,1,PILOT)
        if name=='seed2':verify(c,profile,1,c['task_ids'])
        subprocess.run(command(c,profile,index,pilot=name=='pilot',apply=True),env=env,cwd=PROJECT,check=True)
        verify(c,profile,index,PILOT if name=='pilot' else c['task_ids'])
        print(profile,index,name,'verified, incomplete cases retained',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['plan','prepare','pilot','seed1','seed2','all'],default='plan');p.add_argument('--apply',action='store_true');a=p.parse_args()
    c=json.loads((PROJECT/'configs/qwen38_official_retest.json').read_text());print(f'4 profiles × 5 tasks × {len(c["seeds"])} seed(s). No paid API or cloud.',flush=True)
    if a.phase=='plan':return
    if c.get('retired'):
        raise SystemExit('本次复测已完成并整理，生成入口已退役；只保留四档官方结果。后续实验请使用新的运行编号，参考 docs/qwen38-official-retest.md。')
    if a.phase not in ['prepare'] and not a.apply:p.error('Inference requires --apply')
    env=dict(os.environ);env['OMP_NUM_THREADS']=env['MKL_NUM_THREADS']=str(c['cpu_threads'])
    if a.phase in ['prepare','all']:prepare(c,env)
    if a.phase=='all':
        for name in ['pilot','seed1','seed2']:phase(c,env,name)
    elif a.phase not in ['prepare']:phase(c,env,a.phase)
if __name__=='__main__':main()
