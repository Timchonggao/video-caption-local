"""Create small first-task contact sheets for visual spot checks, without inference."""
import json,math,sys
from pathlib import Path
from PIL import Image,ImageDraw
PROJECT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(PROJECT/'scripts'))
from run_full_v21 import manifest
config=json.loads((PROJECT/'configs/full_v21.json').read_text());folder=PROJECT/'runs'/config['runs']['qwen']['off'];out=PROJECT/'reports/experiments/v2_1/visual-checks';out.mkdir(exist_ok=True)
_,first=manifest();idx=json.loads((folder/'active.json').read_text())['selection'] if (folder/'active.json').exists() else {};created=[]
for tid in first:
    if tid not in idx:continue
    r=json.loads((folder/'versions'/(idx[tid]+'.json')).read_text())
    if r['caption_status']!='success':continue
    b=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text());frames=b['frames'];cols=4
    path=out/(r['sample_id']+'-first.jpg')
    if not path.exists():
        sheet=Image.new('RGB',(cols*320,math.ceil(len(frames)/cols)*285),'white');draw=ImageDraw.Draw(sheet)
        for i,f in enumerate(frames):
            with Image.open(folder/f['path']) as im:
                im.thumbnail((320,260));x=i%cols*320;y=i//cols*285;sheet.paste(im,(x,y));draw.text((x+3,y+263),f"{f['relative_time_s']:.3f}s",fill='black')
        sheet.save(path,quality=85)
    created.append({'task_id':tid,'image':str(path),'qwen_off_caption':r['generated_caption']})
(out/'index.json').write_text(json.dumps(created,ensure_ascii=False,indent=2)+'\n');print('First-task visual evidence:',len(created),'/10')
