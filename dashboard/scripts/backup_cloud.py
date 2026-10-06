"""Read-only snapshot of application D1 tables and the R2 object inventory."""
import json,os
from datetime import datetime,timezone
from pathlib import Path
from cloud_api import query,list_objects
PROJECT=Path(__file__).resolve().parents[2]
def main():
 tables=query("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' ORDER BY name")['results'];backup={'created_at':datetime.now(timezone.utc).isoformat(),'schema':tables,'tables':{},'r2_objects':list_objects()}
 for table in tables:
  name=table['name'];rows=[];offset=0
  while True:
   batch=query('SELECT * FROM "'+name.replace('"','""')+'" LIMIT 1000 OFFSET '+str(offset))['results'];rows.extend(batch)
   if len(batch)<1000:break
   offset+=1000
  backup['tables'][name]=rows
 root=PROJECT/'reports/cloud/backups';root.mkdir(parents=True,exist_ok=True);path=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json');path.write_text(json.dumps(backup,ensure_ascii=False,indent=2)+'\n');os.chmod(path,0o600);print('Snapshot',path,'tables',len(tables),'objects',len(backup['r2_objects']))
if __name__=='__main__':main()
