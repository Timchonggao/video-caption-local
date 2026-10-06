"""Cloud access only when explicitly invoked by a publisher with --apply."""
import json,os,urllib.request
DB_ID='8509d0d7-9004-4089-aebb-9116ffd6678c'
def response(path,payload=None):
 url=f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/"+path
 data=None if payload is None else json.dumps(payload).encode()
 with urllib.request.urlopen(urllib.request.Request(url,data=data,headers={'Authorization':'Bearer '+os.environ['CLOUDFLARE_API_TOKEN'],'Content-Type':'application/json'}),timeout=90) as response:body=json.load(response)
 if not body.get('success'):raise RuntimeError('Cloudflare API rejected request')
 return body
def request(path,payload=None):return response(path,payload)['result']
def query(sql,params=None):return request(f'd1/database/{DB_ID}/query',{'sql':sql,'params':params or []})[0]

def list_objects():
 from urllib.parse import urlencode
 objects=[];cursor='';seen=set()
 while True:
  body=response('r2/buckets/caption-dashboard-videos/objects?'+urlencode({'per_page':1000,**({'cursor':cursor} if cursor else {})}))
  objects.extend(body['result']);info=body.get('result_info',{})
  if not info.get('is_truncated'):return objects
  cursor=info.get('cursor','')
  if not cursor or cursor in seen:raise RuntimeError('Invalid R2 pagination')
  seen.add(cursor)
