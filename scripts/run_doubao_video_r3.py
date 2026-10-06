"""One paid validation call first; only explicit --all expands to five tasks.

Default prepares one local video without calling Ark. No automatic retries/cloud.
Load ~/.config/seed-caption/env before --apply. Existing successes resume.
"""
import argparse,json,os,subprocess,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');p.add_argument('--all',action='store_true')
    p.add_argument('--config',type=Path,default=PROJECT/'configs/doubao_seed21_lite_video_r3_files.json')
    p.add_argument('--retry-unknown',action='store_true',help='Explicitly acknowledge a previous uncertain upload/request')
    a=p.parse_args()
    c=json.loads(a.config.read_text())
    first='sample_01_seg02_sub10__camera2'
    if a.apply and (not os.environ.get('ARK_API_KEY') or os.environ.get('ARK_MODEL')!=c['model']):
        raise ValueError('Load ARK_API_KEY and expected ARK_MODEL on the server; credentials are not printed')
    if a.all and a.apply:
        folder=PROJECT/'runs'/c['run_id'];index=json.loads((folder/'active.json').read_text())['selection'];r=json.loads((folder/'versions'/(index[first]+'.json')).read_text())
        if r['caption_status']!='success' or r.get('finish_reason')!='stop':raise ValueError('First validation must succeed before expansion')
    cmd=[sys.executable,str(PROJECT/'scripts/caption.py'),'--run',c['run_id'],'--provider','doubao','--model',c['model'],
        '--sample',c['sample'],'--camera',c['camera'],'--input-mode','video','--sampling-fps',str(c['requested_fps']),
        '--prompt-id',c['prompt_id'],'--prompt',str(PROJECT/c['prompt_file']),'--background','none','--stop-on-error',
        '--max-new-tokens',str(c['max_new_tokens']),'--max-request-bytes',str(c['max_request_bytes']),
        '--limit','5' if a.all else '1','--max-calls','5' if a.all else '1']
    cmd.extend(['--video-transport',c.get('transport','base64')])
    if c.get('transport') == 'files':
        for key in ['min_frame_tokens','max_frame_tokens','max_video_tokens','file_processing_timeout','file_poll_interval','file_expire_days']:
            if c.get(key) is not None:cmd.extend(['--'+key.replace('_','-'),str(c[key])])
    if a.retry_unknown:cmd.append('--retry-unknown')
    for task in c['tasks']:cmd.extend(['--experiment-task-id',task])
    if not a.all:cmd.extend(['--task-id',first])
    if a.apply:cmd.append('--apply')
    subprocess.run(cmd,cwd=PROJECT,check=True)
    if a.apply:
        folder=PROJECT/'runs'/c['run_id'];index=json.loads((folder/'active.json').read_text())['selection']
        for task in c['tasks'] if a.all else [first]:
            r=json.loads((folder/'versions'/(index[task]+'.json')).read_text())
            if r['caption_status']!='success' or r.get('finish_reason')!='stop':raise ValueError('Request failed/truncated; stopped without automatic retry')
            print(task,r['reported_model'],r['usage'],flush=True)
if __name__=='__main__':main()
