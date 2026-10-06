import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from caption_system.models.token_trace import TokenTrace

class ThinkingTraceTests(unittest.TestCase):
    def trace(self,thinking,ids,times):
        ticks=iter(times);trace=TokenTrace(thinking,[99],[100],clock=lambda:next(ticks))
        trace.put(np.array([[1,2]]))
        for token in ids:trace.put(np.array([token]))
        return trace
    def test_separate_tokens_and_time_partition(self):
        trace=self.trace(True,[10,11,99,20,100],[2,3,4,5,6]);r=trace.metrics(0,8,[10,11,99,20,100])
        self.assertEqual((r['thinking_tokens'],r['caption_tokens'],r['delimiter_tokens'],r['terminal_tokens']),(2,1,1,1))
        self.assertEqual(r['thinking_seconds'],4);self.assertEqual(r['caption_seconds'],4)
        self.assertEqual(r['first_token_seconds'],2);self.assertEqual(r['thinking_decode_seconds'],2)
        self.assertTrue(r['thinking_complete']);self.assertTrue(r['caption_complete'])
    def test_missing_thought_end_and_caption_are_not_complete(self):
        trace=self.trace(True,[10,100],[2,3]);r=trace.metrics(0,4,[10,100])
        self.assertFalse(r['thinking_complete']);self.assertFalse(r['caption_complete']);self.assertEqual(r['caption_tokens'],0)
        trace=self.trace(True,[10,99,100],[2,3,4]);self.assertFalse(trace.metrics(0,5,[10,99,100])['caption_complete'])
    def test_off_counts_and_token_mismatch(self):
        trace=self.trace(False,[10,11,100],[2,3,4]);r=trace.metrics(0,5,[10,11,100])
        self.assertEqual(r['thinking_tokens'],0);self.assertEqual(r['caption_tokens'],2);self.assertEqual(r['caption_seconds'],5)
        with self.assertRaises(ValueError):trace.metrics(0,5,[10,100])
    def test_caption_limit_does_not_consume_thinking_budget(self):
        import torch
        from caption_system.models.qwen import Qwen
        class FakeModel:
            generation_config=SimpleNamespace(eos_token_id=[100])
            def generate(self,input_ids,streamer,stopping_criteria,**kwargs):
                streamer.put(input_ids);output=input_ids
                for token in [10,11,99,20,21,22,100]:
                    output=torch.cat([output,torch.tensor([[token]])],dim=1)
                    stop=stopping_criteria(output,None)
                    streamer.put(torch.tensor([token]))
                    if bool(stop[0]):break
                streamer.end();return output
        q=Qwen.__new__(Qwen);q.torch=torch;q.model=FakeModel();q.thinking=True;q.trace_tokens=True;q.max_tokens=20;q.caption_max_tokens=2
        q.processor=SimpleNamespace(tokenizer=SimpleNamespace(encode=lambda *a,**k:[99]),batch_decode=lambda *a,**k:['reason </think> final caption'],image_processor=SimpleNamespace(patch_size=16))
        with patch.object(torch.cuda,'synchronize'),patch.object(torch.cuda,'device_count',return_value=0):
            _,r=q._generate({'input_ids':torch.tensor([[1,2]])})
        self.assertEqual(r['thinking_tokens'],2);self.assertEqual(r['caption_tokens'],2)
        self.assertFalse(r['caption_complete']);self.assertEqual(r['finish_reason'],'length')
