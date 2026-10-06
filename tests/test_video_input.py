import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from caption_system.video.temporal import temporal_evidence
from caption_system.data.evidence import evidence_index, read_evidence
from caption_system.results.store import sha

class VideoEvidenceTests(unittest.TestCase):
    def test_pts_groups_and_last_frame_padding(self):
        evidence = temporal_evidence([.033, .201, .497])
        self.assertEqual(evidence['encoded_frame_count'],4)
        self.assertEqual(evidence['padding_source_index'],2)
        self.assertAlmostEqual(evidence['groups'][0]['timestamp_s'],.117)
        self.assertEqual(evidence['groups'][1]['relative_times_s'],[.497,.497])
        self.assertEqual(evidence['groups'][0]['display_timestamp_s'],.1)
        self.assertEqual(temporal_evidence([.02,.19])['padding_count'],0)
        for invalid in [[],[.2,.1],[0,0],[float('nan')],[-.01]]:
            with self.assertRaises(ValueError):temporal_evidence(invalid)

    def test_frozen_identity_pixels_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'source';(run/'inputs').mkdir(parents=True);(run/'versions').mkdir()
            media=root/'video.mp4';media.write_bytes(b'source video')
            image=run/'image.png';Image.new('RGB',(32,32),(1,2,3)).save(image,compress_level=1)
            task=dict(task_id='test__camera2',clip_start_time_s=0,clip_end_time_s=1,media_path=str(media))
            bundle={'input_id':'input','task_id':task['task_id'],'source_interval_s':[0,1], 'ready':True,
                'video_sha256':sha(media),'frames':[{'path':'image.png','sha256':sha(image),'pts':1,'source_time_s':.033,'relative_time_s':.033,'deviation_s':.033}]}
            (run/'inputs/input.json').write_text(json.dumps(bundle))
            (run/'active.json').write_text(json.dumps({'selection':{task['task_id']:'result'}}))
            (run/'versions/result.json').write_text(json.dumps({'task_id':task['task_id'],'caption_status':'success','input_id':'input'}))
            self.assertEqual(evidence_index(root,'source',[task['task_id']]),{task['task_id']:'input'})
            frames,meta,_=read_evidence(root,'source','input',task,1)
            self.assertEqual(frames[0].getpixel((0,0)),(1,2,3));self.assertEqual(meta[0]['pts'],1)
            image.write_bytes(b'corrupt')
            with self.assertRaises(ValueError):read_evidence(root,'source','input',task,1)
            with self.assertRaises(ValueError):read_evidence(root,'../source','input',task,1)

    def test_conflicting_pixel_alias_rejected_before_backend(self):
        from caption_system.pipeline.run import main
        with patch('sys.argv',['caption','--run','TEST','--max-pixels','512000','--frame-max-pixels','1000000']):
            with self.assertRaises(SystemExit) as error:main()
        self.assertEqual(error.exception.code,2)

    def test_real_native_processor_without_gpu_or_resampling(self):
        import torch
        from caption_system.models.qwen import Qwen
        from caption_system.config import PATHS
        torch.set_num_threads(4)
        q=Qwen(PATHS['model_path'],512000,512,'video',6)
        frames=[Image.new('RGB',(64,64),(i*30,1,3)) for i in range(3)]
        with tempfile.TemporaryDirectory() as folder:
            request=q.prepare('Describe the observed manipulation.',frames,[.033,.201,.497],folder,[[64,64]]*3)
            tensors=torch.load(request['path'],map_location='cpu',weights_only=True)
            self.assertIn('pixel_values_videos',tensors);self.assertNotIn('pixel_values',tensors)
            self.assertEqual(tensors['video_grid_thw'].tolist()[0][0],2)
            self.assertFalse(request['do_sample_frames']);self.assertFalse(request['do_resize'])
            self.assertEqual(request['encoded_timestamps_s'],[.1,.5])
            self.assertIsNone(q.model)
            q.thinking=True
            on=q.prepare('Describe the observed manipulation.',frames,[.033,.201,.497],folder,[[64,64]]*3)
            on_inputs=torch.load(on['path'],map_location='cpu',weights_only=True)
            torch.testing.assert_close(on_inputs['pixel_values_videos'],tensors['pixel_values_videos'])
            decoded=q.processor.tokenizer.decode(on_inputs['input_ids'][0],skip_special_tokens=False)
            self.assertTrue(decoded.endswith('<think>\n'))
            self.assertTrue(on['thinking_enabled'])
            q.thinking=False
            q.input_mode='images'
            image_request=q.prepare('Describe the observed manipulation.',frames,[.033,.201,.497],folder,[[64,64]]*3)
            self.assertEqual(image_request['image_sizes'],request['image_sizes'])
            image_tensors=torch.load(image_request['path'],map_location='cpu',weights_only=True)
            self.assertIn('pixel_values',image_tensors);self.assertNotIn('pixel_values_videos',image_tensors)
