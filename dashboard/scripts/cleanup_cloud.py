"""Plan old cloud cleanup; requires verified live new site and explicit --apply."""
import argparse,json,sys,urllib.request,urllib.parse
from pathlib import Path
from cloud_api import request,query,list_objects
PROJECT=Path(__file__).resolve().parents[2]
OLD_TABLES={'clips','media','rate_limits','result_details','results','reviews','run_metadata','runs','sample_details','samples','settings','source_annotations','versions'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--site',default='https://video-caption-dashboard.pages.dev');p.add_argument('--apply',action='store_true');a=p.parse_args()
 with urllib.request.urlopen(a.site+'/api/clips',timeout=60) as response:data=json.load(response)
 if data.get('version')!='mcap-v2' or len(data.get('tasks',[]))!=828 or len(data.get('clips',[]))!=138:raise ValueError('Public site is not yet on complete new task-based data; no cleanup')
 state=query("SELECT ready FROM cs_datasets WHERE version='mcap-v2'")['results']
 if not state or state[0]['ready']!=1:raise ValueError('Dataset not ready')
 refs={r['object_key'] for r in query("SELECT object_key FROM cs_media WHERE version='mcap-v2'")['results']}
 if len(refs)!=60:raise ValueError('Expected 60 referenced cloud proxies')
 objects=list_objects();old=[r for r in objects if r['key'].startswith(('videos/','mcap/')) and r['key'] not in refs]
 names={r['name'] for r in query("SELECT name FROM sqlite_master WHERE type='table'")['results']};tables=sorted(OLD_TABLES&names)
 if 'reviews' in tables and query('SELECT COUNT(*) AS n FROM reviews')['results'][0]['n']:
  raise ValueError('Old public reviews now exist; preserve/review them before deleting old tables')
 report={'old_objects':old,'old_tables':tables,'before_bytes':sum(int(r['size']) for r in objects),'delete_bytes':sum(int(r['size']) for r in old),'remaining_bytes':sum(int(r['size']) for r in objects if r not in old),'apply':a.apply}
 path=PROJECT/'reports/cloud/cloud-cleanup-plan.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,indent=2)+'\n');print('Old objects',len(old),'delete GB',round(report['delete_bytes']/1e9,3),'remaining GB',round(report['remaining_bytes']/1e9,3),'tables',tables)
 if not a.apply:return
 # Never use this before backup_cloud.py and new-site playback acceptance.
 backups=list((PROJECT/'reports/cloud/backups').glob('*.json'))
 if not backups:raise ValueError('No cloud database backup found')
 for r in old:
  url='https://api.cloudflare.com/client/v4/accounts/'
  # The objects DELETE endpoint returns a regular Cloudflare JSON response.
  import os
  req=urllib.request.Request(url+os.environ['CLOUDFLARE_ACCOUNT_ID']+'/r2/buckets/caption-dashboard-videos/objects/'+urllib.parse.quote(r['key'],safe='/'),headers={'Authorization':'Bearer '+os.environ['CLOUDFLARE_API_TOKEN']},method='DELETE')
  with urllib.request.urlopen(req,timeout=60) as response:
   if not json.load(response).get('success'):raise RuntimeError('R2 deletion failed')
 for table in tables:query('DROP TABLE "'+table+'"')
 print('Old cloud content cleaned; cs_ tables and referenced proxies preserved')
if __name__=='__main__':main()
