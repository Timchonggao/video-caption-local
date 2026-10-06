"""Read-only experiment audit; write comparison JSON/Markdown and review CSV."""
import csv
import json
import statistics
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def main():
    config = json.loads((PROJECT / 'configs/video_input_comparison.json').read_text())
    if config.get('retired'):
        raise SystemExit('旧四组报告已退役，请运行 scripts/report_qwen_v2.py。')
    evidence, records, groups = {}, {}, {}
    for group, spec in config['groups'].items():
        folder = PROJECT / 'runs' / spec['run_id']
        selected = json.loads((folder / 'active.json').read_text())['selection']
        rows = []
        for task in config['task_ids']:
            record = json.loads((folder / 'versions' / (selected[task] + '.json')).read_text())
            if record['caption_status'] != 'success':
                raise ValueError('Comparison contains failed result')
            bundle = json.loads((folder / 'inputs' / (record['input_id'] + '.json')).read_text())
            signature = [(f['pts'], f['source_time_s'], f['sha256']) for f in bundle['frames']]
            if group == 'A':
                evidence[task] = signature
            elif signature != evidence[task]:
                raise ValueError('Actual frozen frames differ across groups')
            request = bundle['request']
            if request['image_sizes'] != [[768,640]] * len(signature):
                raise ValueError('Frame precision mismatch')
            item = {k:record.get(k) for k in ['task_id','result_id','caption_status','quality_status','generation_seconds',
                'elapsed_seconds','input_tokens','generated_tokens','peak_gpu_allocated_bytes','peak_gpu_reserved_bytes',
                'generated_caption','finish_reason']}
            item.update(group=group,run_id=spec['run_id'],input_mode=spec['input_mode'],frames=len(signature),
                request_bytes=request['request_bytes'],processed_size=[768,640],
                video_timing=request.get('temporal_evidence'),input_note=bundle.get('input_note'))
            rows.append(item)
            records.setdefault(task,{})[group]=item
        groups[group]={'run_id':spec['run_id'],'success':len(rows),'model_calls':len(list((folder/'attempts').glob('*.json'))),
            'generation_total_s':sum(r['generation_seconds'] for r in rows),
            'generation_mean_s':statistics.mean(r['generation_seconds'] for r in rows),
            'input_tokens_mean':statistics.mean(r['input_tokens'] for r in rows),
            'peak_allocated_gib':{str(i):max(r['peak_gpu_allocated_bytes'][str(i)] for r in rows)/2**30 for i in [0,1]}}
    output=PROJECT/'reports/experiments';output.mkdir(exist_ok=True,parents=True)
    result={'groups':groups,'fixed_config':{k:v for k,v in config.items() if k!='groups'},'tasks':records,
            'quality_status':'human_review_pending','cloud_published':False,'new_calls':sum(groups[g]['model_calls'] for g in 'BCD')}
    previous_path = output/'video-input-comparison.json'
    if previous_path.exists():
        previous = json.loads(previous_path.read_text())
        result.update({k:previous[k] for k in ['assistant_initial_review','verification'] if k in previous})
    (output/'video-input-comparison.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    csv_path=output/'video-input-comparison-review.csv'
    if not csv_path.exists():
        with csv_path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['group','run_id','task_id','direction','omission','unsupported_details','final_state','uncertainty','notes'])
            writer.writeheader()
            for task, variants in records.items():
                for group,item in variants.items():writer.writerow({k:item[k] for k in ['group','run_id','task_id']})
    lines=['# v2 视频输入与 Prompt 四组对照','', 'A 复用既有五条；B/C/D 新增 15 条，完成后停止，不扩大到 24 条、不发布云端。各组实际图片哈希、PTS 与尺寸一致。视频内部两帧分组和末尾重复是输入方式的一部分，并非新的真实观察。','', '|组|输入|生成总耗时|平均输入 token|两卡峰值分配显存|','|---|---|---:|---:|---|']
    for g,s in groups.items():
        lines.append(f'|{g}|{config["groups"][g]["input_mode"]}|{s["generation_total_s"]:.1f} 秒|{s["input_tokens_mean"]:.0f}|'+', '.join(f'{k}: {v:.2f} GiB' for k,v in s['peak_allocated_gib'].items())+'|')
    lines+=['', '## 比较限制','', '图片与视频采用不同视觉表示、时间分组与 token 数；结果是输入方式整体影响，不仅是时间文字。新组 GPU 运行前已单独准备 CPU 输入，A 原任务计时包含现场准备，因此不能直接用 elapsed_seconds 的差异声称完整流水线提速。生成时间、实际 token 和峰值显存可独立查看。','', '运行及格式成功不代表语义正确。人工检查动作方向、遗漏、无依据细节、最后状态和局部不确定性；所有 quality_status 保持 unreviewed。CSV 的人工字段留空，不自动打分。五段缺少真实插入/挂上的反向对照。']
    for task,variants in records.items():
        lines+=['','## '+task]
        for g,item in variants.items():lines+=['',f'### {g} · {item["run_id"]}', '',item['generated_caption']]
    if result.get('assistant_initial_review'):
        review = result['assistant_initial_review']
        lines += ['', '## 初查与人工验收建议', '', review['basis'], '', review['recommendation']]
        for task, notes in review['tasks'].items():
            lines += ['', '### '+task, '']
            for key, text in notes.items():
                lines.append('- '+{'direction':'动作方向','omission':'遗漏','unsupported_details':'无依据细节','final_state':'最终状态'}[key]+'：'+text)
    (output/'video-input-comparison.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(groups,indent=2));print('New calls:',result['new_calls'])

if __name__=='__main__':main()
