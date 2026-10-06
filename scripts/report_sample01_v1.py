"""Summarize persisted sample01 baseline evidence without claiming visual accuracy."""
import argparse
import collections
import datetime
import json
import statistics
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', default='qwen-sample01-v1')
    args = parser.parse_args()
    if not args.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.run):
        parser.error('Invalid run ID')
    folder = PROJECT / 'runs' / args.run
    config = json.loads((folder / 'config.json').read_text())
    tasks = [json.loads(line) for line in (folder / 'tasks.jsonl').read_text().splitlines()]
    active = json.loads((folder / 'active.json').read_text())
    records = [json.loads((folder / 'versions' / (rid + '.json')).read_text()) for rid in active.get('selection', active).values()]
    lookup = {r['task_id']: r for r in records}
    evidence = []
    for r in records:
        path = folder / 'inputs' / (r.get('input_id', '') + '.json')
        if not path.is_file():
            evidence.append({'task_id': r['task_id'], 'saved': False})
            continue
        bundle = json.loads(path.read_text())
        lo, hi = bundle['source_interval_s']
        frames = bundle['frames']
        evidence.append({'task_id': r['task_id'], 'saved': True, 'frames': len(frames),
                         'frames_inside_original_interval': all(lo <= f['source_time_s'] < hi for f in frames),
                         'background': bundle['context']['background']['mode'],
                         'history': bundle['context']['history']['status'],
                         'duplicate_frames': sum(f.get('duplicate_of') is not None for f in frames),
                         'max_deviation_s': max(abs(f['deviation_s']) for f in frames)})
    def stats(key):
        values = [r[key] for r in records if isinstance(r.get(key), (int, float))]
        return {'count': len(values), 'min': min(values), 'median': statistics.median(values), 'max': max(values), 'sum': sum(values)} if values else None
    counts = collections.Counter(r['caption_status'] for r in records)
    report = {'run_id': args.run, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'tasks': len(tasks), 'success': counts['success'], 'failed': counts['failed'],
              'pending': len(tasks) - counts['success'] - counts['failed'],
              'quality_status': 'unreviewed', 'runtime': json.loads((folder / 'runtime.json').read_text()) if (folder / 'runtime.json').exists() else {}, 'sampling': {'frames_per_original_clip': config['frames'], 'fps': None},
              'per_camera': {c: dict(collections.Counter(lookup.get(t['task_id'], {}).get('caption_status', 'pending') for t in tasks if t['camera_id'] == c)) for c in [f'camera{i}' for i in range(6)]},
              'generation_seconds': stats('generation_seconds'), 'task_elapsed_seconds': stats('elapsed_seconds'),
              'input_tokens': stats('input_tokens'), 'generated_tokens': stats('generated_tokens'), 'evidence_checks': evidence,
              'results': [{k:r.get(k) for k in ('task_id','camera_id','caption_status','generated_caption','error','sampled_times_s','generation_seconds','elapsed_seconds','input_tokens','generated_tokens','finish_reason')} for r in records]}
    destination = PROJECT / 'reports/experiments'
    destination.mkdir(exist_ok=True)
    (destination / (args.run + '.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    parts = ['# Sample01 v1 纯视觉基线', '', f"运行：{args.run}", '',
             f"任务 {len(tasks)}；成功 {report['success']}；失败 {report['failed']}；待完成 {report['pending']}。", '',
             '每个原始子片段×相机独立生成，均匀请求12帧（不是12 fps），不使用标注背景或历史，不做窗口汇总。读取 CFS 高清原件；处理器每帧512000像素预算，输出256 token上限。', '',
             '质量尚未人工验收。保存成功及输入合法不等于视觉描述准确。下列文字供与视频逐段核对，不作自动质量评分。', '',
             '## 耗时与输入', '', '单任务 elapsed_seconds 包含该任务的输入准备及生成；首条还包含首次加载。各任务累加不等于进程完整墙钟时间，成功复用及进程启动另有开销。', '']
    for key in ('generation_seconds','task_elapsed_seconds','input_tokens','generated_tokens'):
        if report[key]:
            values=report[key]
            parts.append(f"- {key}：中位数 {values['median']:.2f}，范围 {values['min']:.2f}–{values['max']:.2f}。")
    parts.extend(['', '## 分片段与相机检查', ''])
    for clip in dict.fromkeys(t['clip_id'] for t in tasks):
        task = next(t for t in tasks if t['clip_id'] == clip)
        parts.extend([f'### {clip}', '', f"原始片段：{task['clip_start_time_s']}–{task['clip_end_time_s']} 秒；fine_label：{task['subtask_label']}", ''])
        for t in [t for t in tasks if t['clip_id'] == clip]:
            r = lookup.get(t['task_id'])
            text = r.get('generated_caption') or r.get('error', r['caption_status']) if r else '待生成'
            parts.extend([f"**{t['camera_id']}**", text, ''])
    parts.extend(['## 人工评价重点', '', '先核对对象与附着关系、动作顺序、放置与释放、遮挡时的表述，以及12帧是否漏掉短暂操作。再决定下一版只改变哪一个因素。', ''])
    (destination / (args.run + '.md')).write_text('\n'.join(parts))
    print(f"{report['success']}/{len(tasks)} success; {report['failed']} failed; report saved to reports/experiments/")

if __name__ == '__main__':
    main()
