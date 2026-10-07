"""Execute the single user-authorized uncertain request after its run lock is free."""
import argparse,fcntl,json,os,subprocess,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'scripts'))
from run_full_v21 import command

parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--task-id',default='sample_01_seg02_sub13__camera2');args=parser.parse_args()
c=json.loads((PROJECT/'configs/full_v21.json').read_text());rid=c['runs']['doubao']['off'];tid=args.task_id;folder=PROJECT/'runs'/rid
approval_path=PROJECT/'reports/experiments/v2_1/authorized-retries.json'
while True:
    with (folder/'.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:pass
        else:break
    time.sleep(2)
approval=json.loads(approval_path.read_text());entry=next(r for r in approval['retries'] if r['task_id']==tid)
assert entry['task_id']==tid and entry['run_id']==rid and entry['user_authorized'] and entry['authorized_max_additional_calls']==1
index=json.loads((folder/'active.json').read_text())['selection'];old=json.loads((folder/'versions'/(index[tid]+'.json')).read_text())
if old['caption_status']=='success':print('Already successful; no additional call.');sys.exit(0)
previous=[json.loads(p.read_text()) for p in (folder/'attempts').glob('*.json')]
if entry['executed'] or len([a for a in previous if a['task_id']==tid])!=1:raise SystemExit('Authorized single retry already used or attempt history changed; no call made')
entry['executed']=True;approval_path.write_text(json.dumps(approval,ensure_ascii=False,indent=2)+'\n')
cmd=command(c,'doubao','off',apply=True)
for flag in ['--limit','--max-calls']:cmd[cmd.index(flag)+1]='1'
cmd.extend(['--task-id',tid,'--rerun'])
if old.get('execution_status')=='unknown_remote_outcome':cmd.append('--retry-unknown')
print('Executing the single explicitly authorized retry:',tid,flush=True)
subprocess.run(cmd,cwd=PROJECT,check=True)
index=json.loads((folder/'active.json').read_text())['selection'];result=json.loads((folder/'versions'/(index[tid]+'.json')).read_text())
entry.update(caption_status=result['caption_status'],result_id=result['result_id']);approval_path.write_text(json.dumps(approval,ensure_ascii=False,indent=2)+'\n')
if result['caption_status']!='success':raise SystemExit('Single retry failed; retained without another retry')
print('Authorized retry completed successfully.',flush=True)
