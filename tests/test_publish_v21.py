"""Cloud preflight accepts different off/thinking task scopes without cloud calls."""
import json,runpy,tempfile,unittest,sys
from pathlib import Path
from unittest.mock import Mock
from caption_system.config import PROJECT

class PublicationScopeTests(unittest.TestCase):
    def test_stopped_doubao_run_publishes_only_success_and_freezes_identity(self):
        sys.path.insert(0,str(PROJECT/'dashboard/scripts'))
        module=runpy.run_path(str(PROJECT/'dashboard/scripts/publish_mentor.py'))
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);root=project/'dashboard';root.mkdir();meta=project/'metadata';meta.mkdir()
            run_id='doubao-seed21-lite-full-v2_1-off-r2'
            ids=['sample_01_seg01_sub01__camera2','sample_01_seg01_sub02__camera2']
            tasks=[{'task_id':tid,'sample_id':'sample_01','camera_id':'camera2'} for tid in ids]
            (meta/'tasks.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in tasks))
            folder=project/'runs'/run_id;(folder/'versions').mkdir(parents=True);(folder/'inputs').mkdir()
            (folder/'config.json').write_text(json.dumps({'background':'none','contextual':False}))
            run={'id':run_id,'model_key':'doubao','prompt_id':'baseline-v2-1','camera':'camera2','experiment_task_ids':ids}
            rows=[{'task_id':ids[0],'run_id':run_id,'result_id':'OK','caption_status':'success'},
                  {'task_id':ids[1],'run_id':run_id,'result_id':'FAILED','caption_status':'failed'}]
            (folder/'versions/OK.json').write_text(json.dumps({**rows[0],'input_id':'INPUT'}))
            (folder/'inputs/INPUT.json').write_text(json.dumps({'frames':[]}))
            fn=module['prepare'];fn.__globals__.update(PROJECT=project,ROOT=root,load_runs=lambda _: ([run],rows),
                    sampling_evidence=lambda *args:{'status':'result','ready':True,'frames':[],'provider_sampling_known':False})
            config={'samples':['sample_01'],'camera':'camera2','task_ids':ids,'run_ids':[run_id],
                    'published_result_counts':{run_id:1},'fixed_prompt_id':'baseline-v2-1','jpeg_max_edge':640,'jpeg_quality':75}
            packets,paths,plan=fn(config)
            self.assertEqual(plan['results'],1)
            self.assertEqual([r['result_id'] for r in packets[0]['results']],['OK'])
            snapshot=module['release_snapshot'](packets)
            path=root/'release.json'
            path.write_text(json.dumps(snapshot))
            module['check_snapshot'](path,snapshot)
            rows[0]['result_id']='CHANGED'
            with self.assertRaises(ValueError):module['check_snapshot'](path,module['release_snapshot']([{'run':run,'results':rows[:1]}]))

    def test_whole_dataset_off_and_sparse_thinking_are_validated_independently(self):
        sys.path.insert(0,str(PROJECT/'dashboard/scripts'))
        module=runpy.run_path(str(PROJECT/'dashboard/scripts/publish_mentor.py'))
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);root=project/'dashboard';root.mkdir();meta=project/'metadata';meta.mkdir()
            ids=['sample_01_seg01_sub01__camera2','sample_02_seg01_sub01__camera2']
            tasks=[{'task_id':tid,'sample_id':tid.split('_seg')[0],'camera_id':'camera2'} for tid in ids]
            (meta/'tasks.jsonl').write_text(''.join(json.dumps(t)+'\n' for t in tasks))
            runs=[{'id':'TEST-OFF','model_key':'doubao','prompt_id':'baseline-v2-1','camera':'camera2','experiment_task_ids':ids},
                  {'id':'TEST-ON','model_key':'doubao','prompt_id':'baseline-v2-1','camera':'camera2','experiment_task_ids':ids[:1]}]
            results=[]
            for run in runs:
                folder=project/'runs'/run['id'];(folder/'versions').mkdir(parents=True);(folder/'inputs').mkdir()
                (folder/'config.json').write_text(json.dumps({'background':'none','contextual':False}))
                for i,tid in enumerate(run['experiment_task_ids']):
                    rid='RESULT'+str(i);inp='INPUT'+str(i)
                    row={'task_id':tid,'run_id':run['id'],'result_id':rid,'caption_status':'success','generated_caption':'Action.'}
                    results.append(row);(folder/'versions'/(rid+'.json')).write_text(json.dumps({**row,'input_id':inp}))
                    (folder/'inputs'/(inp+'.json')).write_text(json.dumps({'frames':[]}))
            fn=module['prepare'];g=fn.__globals__;g.update(PROJECT=project,ROOT=root,load_runs=lambda _: (runs,results),
                    sampling_evidence=lambda *args:{'status':'result','ready':True,'frames':[],'provider_sampling_known':False})
            forbidden=Mock(side_effect=AssertionError('Preflight must not access cloud'));g['query']=g['upload']=g['list_objects']=forbidden
            config={'samples':['sample_01','sample_02'],'camera':'camera2','task_ids':ids,'run_ids':['TEST-OFF','TEST-ON'],'fixed_prompt_id':'baseline-v2-1','jpeg_max_edge':640,'jpeg_quality':75}
            packets,paths,plan=fn(config)
            self.assertEqual([len(p['results']) for p in packets],[2,1]);self.assertEqual(plan['results'],3)
            self.assertEqual(plan['video_uploads'],0);self.assertEqual(paths,{})
            results.pop()
            with self.assertRaises(ValueError):fn(config)
            forbidden.assert_not_called()
