"""Explicit cloud publishing: videos/metadata or task-keyed results; dry-run default."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT.parent;sys.path.insert(0,str(PROJECT/'src'))
from caption_system.config import PATHS,VERSION
from caption_system.data.tasks import read_jsonl
from caption_system.results.repository import load_runs
from cloud_api import query,list_objects
from remote_upload import upload

def main():
 p=argparse.ArgumentParser();p.add_argument('--run');p.add_argument('--apply',action='store_true');p.add_argument('--max-storage-gb',type=float,default=8);a=p.parse_args()
 clips=read_jsonl(PROJECT/'metadata/clips.jsonl');tasks=read_jsonl(PROJECT/'metadata/tasks.jsonl');samples=json.loads((PROJECT/'metadata/samples.json').read_text())
 if a.run:
  runs,results=load_runs(tasks);runs=[r for r in runs if r['id']==a.run];results=[r for r in results if r['run_id']==a.run]
  if not runs:raise ValueError('Run not found')
  print('Publish run',a.run,'results',len(results))
  if not a.apply:return
  valid={r['task_id'] for r in query('SELECT task_id FROM cs_tasks WHERE version=?',[VERSION])['results']}
  if any(r['task_id'] not in valid for r in results):raise ValueError('Publish dataset first')
  config=json.dumps({k:v for k,v in runs[0].items() if k!='id'},ensure_ascii=False)
  existing=query('SELECT config FROM cs_runs WHERE id=?',[a.run])['results']
  if existing and existing[0]['config']!=config:raise ValueError('Run metadata differs; use new run ID')
  query('INSERT INTO cs_runs VALUES (?,?) ON CONFLICT(id) DO NOTHING',[a.run,config])
  for r in results:
   text=json.dumps(r,ensure_ascii=False);old=query('SELECT data FROM cs_results WHERE version=? AND task_id=? AND run_id=?',[VERSION,r['task_id'],a.run])['results']
   if old and old[0]['data']!=text:raise ValueError('Published result differs; use new run ID')
   query('INSERT INTO cs_results VALUES (?,?,?,?) ON CONFLICT DO NOTHING',[VERSION,r['task_id'],a.run,text])
  return
 proxy_path=PROJECT/'metadata/cloud_proxies.json'
 if not proxy_path.exists():raise ValueError('Prepare cloud-only display proxies first')
 proxy_report=json.loads(proxy_path.read_text())
 if not proxy_report.get('complete'):raise ValueError('All 60 proxy videos must be prepared and validated first')
 proxies={r['id']:r for r in proxy_report['videos']};paths={};media=[]
 for inv in samples:
  for m in inv['media']:
   if m['kind']!='video':continue
   proxy=proxies.get(m['id'])
   if not proxy:raise ValueError('Missing cloud proxy '+m['id'])
   path=Path(proxy['path'])
   if not path.resolve().is_relative_to(Path(PATHS['proxy_root']).resolve()):raise ValueError('Cloud video must come from proxy_root')
   digest=hashlib.sha256(path.read_bytes()).hexdigest()
   if digest!=proxy['proxy_sha256']:raise ValueError('Cloud proxy changed after validation')
   key='preview/'+proxy_report['profile']+'/'+digest+'.mp4';paths[key]=path;media.append((m['id'],key))
 print('Dataset:',len(clips),'clips,',len(tasks),'tasks,',len(paths),'videos,',round(sum(p.stat().st_size for p in paths.values())/1e9,3),'GB')
 if not a.apply:return
 # Account bucket preflight: conservative upper bound; no upload if above the cap.
 items=list_objects()
 existing={r['key']:int(r['size']) for r in items};projected=sum(existing.values())+sum(p.stat().st_size for key,p in paths.items() if key not in existing)
 if projected>a.max_storage_gb*1e9:raise ValueError(f'Projected bucket {projected/1e9:.3f} GB exceeds {a.max_storage_gb} GB; no upload performed')
 upload(paths);query((ROOT/'migrations/0100_task_system.sql').read_text())
 fingerprint=hashlib.sha256(json.dumps({'clips':clips,'tasks':[{k:t[k] for k in ['task_id','clip_id','camera_id','media_id']} for t in tasks],'proxy_profile':proxy_report['profile'],'video_hashes':[r['proxy_sha256'] for r in proxy_report['videos']]},sort_keys=True).encode()).hexdigest()
 known=query('SELECT fingerprint FROM cs_datasets WHERE version=?',[VERSION])['results']
 if known and known[0]['fingerprint']!=fingerprint:raise ValueError('Dataset content changed; use a new data version')
 query('INSERT INTO cs_datasets VALUES (?,?,0) ON CONFLICT DO NOTHING',[VERSION,fingerprint])
 def insert(table,values):
  for i in range(0,len(values),12):
   batch=values[i:i+12];width=len(batch[0]);query('INSERT INTO '+table+' VALUES '+','.join(['('+','.join(['?']*width)+')']*len(batch))+' ON CONFLICT DO NOTHING',[value for row in batch for value in row])
 insert('cs_clips',[[VERSION,c['clip_id'],json.dumps({k:v for k,v in c.items() if k not in ['mcap_path','media_path']},ensure_ascii=False)] for c in clips])
 insert('cs_tasks',[[VERSION,t['task_id'],t['clip_id'],t['camera_id'],t['media_id'],json.dumps({k:t[k] for k in ['task_id','clip_id','sample_id','camera_id','media_id']})] for t in tasks])
 for inv in samples:
  sid=inv['sample_id'];public={'sample_id':sid,'media':[{**{k:v for k,v in m.items() if k!='file'},**{k:proxies[m['id']][k] for k in ['width','height','source_to_video_offset_s']}} for m in inv['media'] if m['kind']=='video']};query('INSERT INTO cs_samples VALUES (?,?,?,?) ON CONFLICT DO NOTHING',[VERSION,sid,(PROJECT/'metadata/annotations'/f'{sid}.json').read_text(),json.dumps(public)])
 insert('cs_media',[[VERSION,mid,key] for mid,key in media])
 query('UPDATE cs_datasets SET ready=1 WHERE version=?',[VERSION])
if __name__=='__main__':main()
