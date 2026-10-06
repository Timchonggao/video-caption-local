"""Prepare immutable display proxies. Original inference videos are never overwritten."""
import argparse,json,subprocess,hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from caption_system.config import PROJECT,PATHS
from caption_system.results.store import sha

def probe(path):
 return json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,start_time,duration,nb_frames','-of','json',str(path)]))['streams'][0]

def timeline(path):
 value=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(path)]))
 return [float(frame['best_effort_timestamp_time']) for frame in value['frames']]

def convert(item,config):
 sid,media=item;source=Path(PATHS['media_root'])/sid/media['file'];folder=Path(PATHS['proxy_root'])/config['profile']/sid;folder.mkdir(parents=True,exist_ok=True);path=folder/(media['camera']+'.mp4');recordpath=path.with_suffix('.json')
 signature={'source_sha256':sha(source),'encoding':config}
 if recordpath.exists() and path.exists():
  existing=json.loads(recordpath.read_text())
  if existing.get('signature')==signature and existing.get('proxy_sha256')==sha(path):return existing
 temp=path.with_name(media['camera']+'.partial.mp4');divisor=config['dimension_divisor']
 command=['ffmpeg','-v','error','-y','-copyts','-i',str(source),'-map','0:v:0','-an','-vf',f'scale=trunc(iw/{divisor}/2)*2:trunc(ih/{divisor}/2)*2','-c:v',config['codec'],'-preset',config['preset'],'-crf',str(config['crf']),'-threads',str(config['threads_per_video']),'-pix_fmt',config['pixel_format'],'-bf','0','-g','30','-fps_mode','passthrough','-enc_time_base','1:1000000','-video_track_timescale','1000000','-movflags','+faststart',str(temp)]
 try:
  subprocess.run(command,check=True,capture_output=True)
  original_times=timeline(source);proxy_times=timeline(temp)
  if len(original_times)!=len(proxy_times) or not original_times:raise ValueError('Frame count changed')
  max_error=max(abs(a-b) for a,b in zip(original_times,proxy_times))
  if max_error>.001:raise ValueError('Frame timeline changed')
  dimensions=probe(temp);temp.replace(path)
  record={'id':media['id'],'sample_id':sid,'camera_id':media['camera'],'path':str(path),'width':int(dimensions['width']),'height':int(dimensions['height']),'source_to_video_offset_s':float(media['first_available_time_s'])-float(dimensions['start_time']),'first_available_time_s':media['first_available_time_s'],'last_available_time_s':media['last_available_time_s'],'source_bytes':source.stat().st_size,'proxy_bytes':path.stat().st_size,'frames':len(proxy_times),'max_timestamp_error_s':max_error,'proxy_sha256':sha(path),'signature':signature}
  recordpath.write_text(json.dumps(record,indent=2)+'\n');return record
 finally:temp.unlink(missing_ok=True)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);args=parser.parse_args();config=json.loads((PROJECT/'configs/cloud_video.json').read_text());inventories=json.loads((PROJECT/'metadata/samples.json').read_text());jobs=[(r['sample_id'],m) for r in inventories for m in sorted((m for m in r['media'] if m['kind']=='video'),key=lambda m:m['camera'])]
 if args.limit:jobs=jobs[:args.limit]
 output=[]
 with ThreadPoolExecutor(max_workers=config['workers']) as pool:
  for record in pool.map(lambda item:convert(item,config),jobs):
   output.append(record);print(record['id'],f"{record['width']}x{record['height']}",round(record['proxy_bytes']/1e6,2),'MB',flush=True)
 report={'profile':config['profile'],'complete':len(output)==sum(m['kind']=='video' for r in inventories for m in r['media']),'videos':output,'source_bytes':sum(r['source_bytes'] for r in output),'proxy_bytes':sum(r['proxy_bytes'] for r in output)}
 (PROJECT/'metadata/cloud_proxies.json').write_text(json.dumps(report,indent=2)+'\n');print('Proxy GB',round(report['proxy_bytes']/1e9,3),flush=True)
if __name__=='__main__':main()
