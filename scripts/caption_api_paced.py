"""Operational Ark pacing only; no automatic retry or changed generation settings."""
import fcntl,json,sys,time
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/'src'))
from caption_system.config import PATHS
from caption_system.models.api import Api,RequestFailure
from caption_system.results.atomic import atomic_json
INTERVAL=10.0
state=Path(PATHS['cache_root'])/'v2_1/ark-request-pacing.json'
original=Api._send

def gate(extra=0):
    state.parent.mkdir(parents=True,exist_ok=True)
    with state.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        data=json.loads(state.read_text()) if state.exists() else {'last_start':time.time()+20}
        if extra:
            atomic_json(state,{'last_start':time.time()+extra});return 0
        wait=max(0,INTERVAL-(time.time()-data['last_start']))
        if wait:time.sleep(wait)
        atomic_json(state,{'last_start':time.time(),'min_interval_seconds':INTERVAL})
        return wait

def paced(self,body,sizes):
    waited=gate() if self.provider=='doubao' else 0
    self.runtime['client_rate_guard']={'min_interval_seconds':INTERVAL,'wait_seconds_recorded_separately':True}
    try:text,extra=original(self,body,sizes)
    except RequestFailure as error:
        if '429' in str(error):gate(extra=30)
        raise
    extra['client_rate_wait_seconds']=waited
    return text,extra

Api._send=paced
from caption_system.pipeline.run import main
if __name__=='__main__':main()
