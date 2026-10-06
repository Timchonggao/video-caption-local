"""Measured thinking off/on on five frozen video tasks. No paid API or cloud.

Default plan; prepare performs CPU preparation, then off, on-pilot, on-rest
require --apply. Stop after failure, no automatic budget increase or rerun.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def check(config,group,subset):
    folder=PROJECT/'runs'/config['groups'][group]['run_id'];selection=json.loads((folder/'active.json').read_text())['selection']
    for task in subset:
        row=json.loads((folder/'versions'/(selection[task]+'.json')).read_text())
        if row['caption_status']!='success' or not row.get('caption_complete') or not row.get('thinking_complete'):
            raise ValueError('Incomplete thought/caption; no automatic retry or budget change')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=['plan','prepare','off','on-pilot','on-rest'],default='plan');p.add_argument('--apply',action='store_true');a=p.parse_args()
    c=json.loads((PROJECT/'configs/qwen_v2_thinking.json').read_text())
    if c.get('retired'):
        raise SystemExit('旧贪心思考对照已退役并清理；当前采用四档官方采样结果，见 docs/qwen38-official-retest.md。')
    print('Same five tasks; video+r3, 6fps, 512000 pixels; total 4096 tokens and final caption 512 tokens.',flush=True)
    if a.phase=='plan':return
    if a.phase!='prepare' and not a.apply:p.error('Inference requires --apply')
    groups=['off','on'] if a.phase=='prepare' else ['off' if a.phase=='off' else 'on']
    pilot=['sample_01_seg02_sub10__camera2','sample_01_seg02_sub12__camera2']
    env=dict(os.environ);env['OMP_NUM_THREADS']=env['MKL_NUM_THREADS']=str(c['cpu_threads'])
    for group in groups:
        if a.phase=='on-rest':check(c,'on',pilot)
        cmd=[sys.executable,str(PROJECT/'scripts/caption.py'),'--run',c['groups'][group]['run_id'],'--provider','qwen','--sample',c['sample'],'--camera',c['camera'],
             '--input-mode','video','--sampling-fps',str(c['sampling_fps']),'--frame-max-pixels',str(c['frame_max_pixels']),
             '--prompt-id','baseline-v2','--prompt',str(PROJECT/c['prompt_file']),'--evidence-run',c['evidence_run'],'--background','none',
             '--max-new-tokens',str(c['max_new_tokens']),'--caption-max-tokens',str(c['caption_max_tokens']),'--trace-tokens','--max-request-bytes',str(c['max_request_bytes']),
             '--limit','5','--max-calls','5','--stop-on-error']
        for task in c['task_ids']:cmd.extend(['--experiment-task-id',task])
        if group=='on':cmd.append('--thinking')
        selected=pilot if a.phase=='on-pilot' else c['task_ids']
        if a.phase=='on-pilot':
            for task in selected:cmd.extend(['--task-id',task])
        if a.phase!='prepare':cmd.append('--apply')
        subprocess.run(cmd,env=env,cwd=PROJECT,check=True)
        if a.phase!='prepare':check(c,group,selected)
        else:
            folder=PROJECT/'runs'/c['groups'][group]['run_id'];preview=json.loads((folder/'preview.json').read_text())
            if len(preview['inputs'])!=5 or not all(x.get('ready') for x in preview['inputs']):raise ValueError('CPU preparation failed')
            print(group, 'five inputs prepared',flush=True)
if __name__=='__main__':main()
