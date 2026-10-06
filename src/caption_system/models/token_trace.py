"""Token-boundary accounting. Times are host observations, not kernel profiling."""
import time

class TokenTrace:
    def __init__(self, thinking, end_ids, eos_ids, clock=time.perf_counter):
        self.thinking=thinking;self.end_ids=list(end_ids);self.eos_ids=set(eos_ids)
        self.clock=clock;self.ids=[];self.times=[];self.prompt_received=False;self.close_position=None
    def put(self,value):
        values=value.tolist()
        if not self.prompt_received:
            self.prompt_received=True
            return
        if values and isinstance(values[0],list):
            if len(values)!=1:raise ValueError('Trace supports one sequence')
            values=values[0]
        now=self.clock()
        for token in values:
            self.ids.append(int(token));self.times.append(now)
            if self.thinking and self.close_position is None and self.ids[-len(self.end_ids):]==self.end_ids:
                self.close_position=len(self.ids)
    def end(self):pass
    def metrics(self,start,end,generated_ids):
        if self.ids!=list(generated_ids):raise ValueError('Token trace does not match generated output')
        terminal=sum(t in self.eos_ids for t in self.ids)
        stopped=bool(self.ids and self.ids[-1] in self.eos_ids)
        if self.thinking:
            position=self.close_position
            thought=(position-len(self.end_ids)) if position is not None else len(self.ids)-terminal
            caption_ids=self.ids[position:] if position is not None else []
            boundary=self.times[position-1] if position is not None else end
        else:
            position=0;thought=0;caption_ids=self.ids;boundary=start
        caption=sum(t not in self.eos_ids for t in caption_ids)
        first=self.times[0] if self.times else end
        return {'thinking_enabled':self.thinking,'thinking_tokens':thought,'caption_tokens':caption,
                'delimiter_tokens':len(self.end_ids) if self.thinking and position is not None else 0,
                'terminal_tokens':terminal,'thinking_complete':not self.thinking or position is not None,
                'caption_complete':stopped and caption>0 and (not self.thinking or position is not None),
                'first_token_seconds':first-start,
                'thinking_seconds':boundary-start if self.thinking else 0.0,
                'thinking_decode_seconds':max(0,boundary-first) if self.thinking else 0.0,
                'caption_seconds':end-boundary,
                'timing_note':'Host token-boundary timing. Thinking phase includes visual prefill; off caption phase includes prefill. Tracing adds host synchronization; compare identically traced runs.'}
