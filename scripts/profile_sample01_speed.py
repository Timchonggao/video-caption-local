import sys,json,time,tempfile,statistics
from pathlib import Path
sys.path.insert(0,'/root/workspace/video-caption-local/project/src')
from caption_system.results.store import sha
from caption_system.video.sampling import sample_evidence
from caption_system.models.qwen import Qwen
root=Path('/root/workspace/video-caption-local/project'); run=root/'runs/qwen-sample01-v1'
def timed(fn):
 s=time.perf_counter(); v=fn(); return v,time.perf_counter()-s
bundles=[json.loads(p.read_text()) for p in sorted((run/'inputs').glob('*.json'))]
report={'method':'Isolated warm-cache CPU benchmarks; no model generation, no formal run modifications','inputs':len(bundles)}
def scan(old_logic):
 count=0; size=0
 for b in bundles:
  if not old_logic and b.get('preparation_key') != 'nonmatching-key': continue
  for m in b['frames']:
   p=run/m['path']; assert sha(p)==m['sha256']; count+=1;size+=p.stat().st_size
 return {'hashed_frames':count,'bytes_read':size}
report['cache_old'],report['cache_old_seconds']=timed(lambda:scan(True))
report['cache_key_first'],report['cache_key_first_seconds']=timed(lambda:scan(False))
print('Cache:',json.dumps(report),flush=True)
import torch
torch.set_num_threads(4)
paths=json.loads((root/'configs/paths.json').read_text()); backend,init=timed(lambda:Qwen(paths['model_path'],512000,256));report['processor_initialization_seconds']=init
alltasks=[json.loads(l) for l in (run/'tasks.jsonl').read_text().splitlines()]; cam=[t for t in alltasks if t['camera_id']=='camera0']; cam.sort(key=lambda t:t['clip_duration_s']);tasks=[cam[0],cam[len(cam)//2],cam[-1]]
report['tasks']=[]
with tempfile.TemporaryDirectory(prefix='caption-speed-') as tmp:
 folder=Path(tmp)
 for task in tasks:
  b=next(x for x in bundles if x['task_id']==task['task_id']); row={'task_id':task['task_id'],'duration_s':task['clip_duration_s']}
  (frames,meta),row['decode_select_rgb_seconds']=timed(lambda:sample_evidence(task,12,1.0))
  for level in (6,1,0):
   def save():
    for i,f in enumerate(frames): f.save(folder/f'{i}.png',compress_level=level)
   _,row[f'png_level_{level}_seconds']=timed(save)
   row[f'png_level_{level}_bytes']=sum((folder/f'{i}.png').stat().st_size for i in range(12))
  inputs,row['processor_seconds']=timed(lambda:backend._inputs(b['prompt'],frames,[m['relative_time_s'] for m in meta]))
  p=folder/'inputs.pt'; _,row['tensor_save_seconds']=timed(lambda:torch.save(dict(inputs),p)); _,row['tensor_hash_seconds']=timed(lambda:sha(p));loaded,row['tensor_load_seconds']=timed(lambda:torch.load(p,map_location='cpu',weights_only=True));row['tensor_bytes']=p.stat().st_size
  report['tasks'].append(row);print(json.dumps(row),flush=True)
(root/'reports/performance/sample01-v1-stage-profile.json').write_text(json.dumps(report,indent=2))
