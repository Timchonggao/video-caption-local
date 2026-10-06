"""Sampling controls with task-stable RNG and generated-token presence penalty."""
import hashlib,json
from transformers.generation.logits_process import LogitsProcessor


def task_seed(base_seed,task_id):
    if not isinstance(base_seed,int) or base_seed<0 or not isinstance(task_id,str) or not task_id:
        raise ValueError('Invalid seed/task identity')
    body=json.dumps([base_seed,task_id],separators=(',',':')).encode()
    return int.from_bytes(hashlib.sha256(body).digest()[:8],'big') & ((1<<63)-1)


class GeneratedPresencePenalty(LogitsProcessor):
    def __init__(self,prompt_length,penalty):
        self.prompt_length=prompt_length;self.penalty=penalty
    def __call__(self,input_ids,scores):
        if not self.penalty or input_ids.shape[1]<=self.prompt_length:return scores
        import torch
        seen=torch.zeros_like(scores,dtype=torch.bool)
        seen.scatter_(1,input_ids[:,self.prompt_length:],True)
        return scores-self.penalty*seen.to(scores.dtype)
