"""Upload immutable video objects through the same R2 REST API used by Wrangler."""
import mimetypes,os,time,urllib.request,urllib.error,urllib.parse,http.client
from concurrent.futures import ThreadPoolExecutor

def upload(paths, existing_keys=None):
    account=os.environ['CLOUDFLARE_ACCOUNT_ID'];token=os.environ['CLOUDFLARE_API_TOKEN']
    base=f'https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/caption-dashboard-videos/objects/'
    def transfer(item):
        key,path=item;url=base+urllib.parse.quote(key,safe='/');headers={'Authorization':'Bearer '+token}
        for attempt in range(6):
            try:
                if existing_keys is not None:
                    if key in existing_keys:return 'existing'
                else:
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=45):return 'existing'
                    except urllib.error.HTTPError as e:
                        if e.code!=404:raise
                with urllib.request.urlopen(urllib.request.Request(url,data=path.read_bytes(),headers={**headers,'Content-Type':mimetypes.guess_type(str(path))[0] or 'application/octet-stream'},method='PUT'),timeout=180) as response:response.read()
                return 'uploaded'
            except (urllib.error.URLError,TimeoutError,http.client.RemoteDisconnected,ConnectionResetError) as e:
                if isinstance(e,urllib.error.HTTPError) and e.code not in (429,500,502,503,504):raise RuntimeError(f'R2 object {key}: HTTP {e.code}') from None
                if attempt==5:raise RuntimeError(f'R2 upload failed for {key}') from None
                time.sleep(2**attempt)
    counts={'existing':0,'uploaded':0}
    with ThreadPoolExecutor(max_workers=int(os.environ.get("MCAP_UPLOAD_WORKERS","4"))) as pool:
        for i,status in enumerate(pool.map(transfer,paths.items()),1):
            counts[status]+=1
            if i%20==0 or i==len(paths):print(f'R2: {i}/{len(paths)}, 新增 {counts["uploaded"]}, 已存在 {counts["existing"]}',flush=True)
    return counts
