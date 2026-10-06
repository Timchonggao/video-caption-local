"""Read the accepted video+r3 baseline without retired run dependencies."""
import json,statistics
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[1]

def main():
    name='qwen-sample01-v2-video-r3';folder=PROJECT/'runs'/name
    config=json.loads((folder/'config.json').read_text());active=json.loads((folder/'active.json').read_text())['selection'];rows={}
    for task,result in active.items():
        r=json.loads((folder/'versions'/(result+'.json')).read_text());b=json.loads((folder/'inputs'/(r['input_id']+'.json')).read_text())
        if r['caption_status']!='success':raise ValueError('Baseline includes failed result')
        for f in b['frames']:
            if not (folder/f['path']).is_file():raise ValueError('Baseline is not self-contained')
        rows[task]={'result_id':r['result_id'],'generated_caption':r['generated_caption'],'frames':len(b['frames']),
            'generation_seconds':r['generation_seconds'],'input_tokens':r['input_tokens'],'generated_tokens':r['generated_tokens'],
            'peak_gpu_allocated_bytes':r['peak_gpu_allocated_bytes'],'processed_sizes':r['processed_sizes']}
    report={'run_id':name,'accepted_method':'video+r3','thinking':False,'sampling_fps':6,'completed':len(rows),'full_sample_tasks':24,
        'prompt':config['prompt_modules'][0]['text'],'generation_total_s':sum(r['generation_seconds'] for r in rows.values()),'results':rows,
        'quality_status':'unreviewed','interpretation':'方案选择已收敛，不等于准确性问题已全部解决；保留为 thinking 对照基线。'}
    out=PROJECT/'reports/experiments';(out/'qwen-v2-video-r3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    lines=['# Qwen v2 已确认基线：视频＋r3','',report['interpretation'],'','保留 camera2、6 fps、同一六部分 r3、512000 每帧像素预算、512 token 上限，thinking 关闭。当前五段成功，尚未扩大到完整 24 条。运行配置保留历史输入来源标识；当前图片和张量均在本运行内，不依赖已清理的探索目录读取。','', '|任务|帧数|生成耗时|输入/输出 token|','|---|---:|---:|---:|']
    for task,r in rows.items():lines.append(f'|{task}|{r["frames"]}|{r["generation_seconds"]:.2f} 秒|{r["input_tokens"]}/{r["generated_tokens"]}|')
    for task,r in rows.items():lines+=['','## '+task,'',r['generated_caption']]
    (out/'qwen-v2-video-r3.md').write_text('\n'.join(lines)+'\n')
    print('Accepted Qwen v2 baseline:',len(rows),'results')
if __name__=='__main__':main()
