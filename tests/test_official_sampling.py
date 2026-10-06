import tempfile,unittest,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import torch
from caption_system.models.sampling import GeneratedPresencePenalty,task_seed

class OfficialSamplingTests(unittest.TestCase):
    def test_presence_only_generated_and_once(self):
        scores=torch.tensor([[1.,2.,3.,4.,5.,6.]])
        processor=GeneratedPresencePenalty(2,1.5)
        actual=processor(torch.tensor([[1,2,3,3,4]]),scores)
        torch.testing.assert_close(actual,torch.tensor([[1.,2.,3.,2.5,3.5,6.]]))
        self.assertIs(GeneratedPresencePenalty(2,0)(torch.tensor([[1,2,3]]),scores),scores)
        self.assertIs(processor(torch.tensor([[1,2]]),scores),scores)
    def test_seed_is_stable_order_independent(self):
        a=task_seed(20261006,'taskA');b=task_seed(20261006,'taskB')
        self.assertEqual(a,task_seed(20261006,'taskA'));self.assertNotEqual(a,b);self.assertNotEqual(a,task_seed(20261007,'taskA'))
        torch.manual_seed(a);first=torch.rand(4);torch.manual_seed(b);torch.rand(100)
        torch.manual_seed(task_seed(20261006,'taskA'));torch.testing.assert_close(first,torch.rand(4))
    def test_actual_sampling_arguments_and_task_seed(self):
        from caption_system.models.qwen import Qwen
        captured={}
        class Fake:
            def generate(self,**kwargs):
                captured.update(kwargs)
                return torch.tensor([[1,2,3,4]])
        q=Qwen.__new__(Qwen);q.torch=torch;q.model=Fake();q.trace_tokens=False;q.max_tokens=10;q.current_task_id='taskA';q.thinking=False;q.reasoning_effort=None
        q.sampling={'do_sample':True,'temperature':.7,'top_p':.8,'top_k':20,'min_p':0,'presence_penalty':1.5,'repetition_penalty':1,'base_seed':20261006}
        q.processor=SimpleNamespace(image_processor=SimpleNamespace(patch_size=16),batch_decode=lambda *a,**kw:['caption'])
        with patch.object(torch.cuda,'synchronize'),patch.object(torch.cuda,'device_count',return_value=0):
            _,result=q._generate({'input_ids':torch.tensor([[1,2]])})
        for k in ['do_sample','temperature','top_p','top_k','min_p','repetition_penalty']:self.assertEqual(captured[k],q.sampling[k])
        self.assertNotIn('presence_penalty',captured);self.assertIsInstance(captured['logits_processor'][0],GeneratedPresencePenalty)
        self.assertEqual(result['task_seed'],task_seed(20261006,'taskA'))
    def test_real_effort_templates(self):
        from caption_system.models.qwen import Qwen
        from caption_system.config import PATHS
        from PIL import Image
        q=Qwen(PATHS['model_path'],512000,4096,'video',6,True,True,512,None,'low',False)
        frames=[Image.new('RGB',(64,64))]*2
        with tempfile.TemporaryDirectory() as folder:
            summaries={}
            for effort in ['low','medium','xhigh']:
                q.reasoning_effort=effort
                r=q.prepare('SAME R3',frames,[.01,.18],folder)
                summaries[effort]=r['template_summary']
                self.assertEqual(r['template_summary']['effective_reasoning_effort'],effort)
                self.assertFalse(r['template_summary']['template_kwargs']['preserve_thinking'])
                if effort in ['low','xhigh']:self.assertIn('Reasoning effort is set to '+effort,Path(folder,'rendered_template.txt').read_text())
            self.assertEqual(len({x['pre_expansion_sha256'] for x in summaries.values()}),3)
            q.thinking=False;q.reasoning_effort=None
            q.prepare('SAME R3',frames,[.01,.18],folder)
            self.assertNotIn('Reasoning effort',Path(folder,'rendered_template.txt').read_text())
