"""Read-only v2.1 whole-clip versus v3 window comparison for human video review."""
import csv
import io
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
from caption_system.results.atomic import atomic_json, atomic_text
from run_v3_window_off import SPEC_PATH, selected_tasks, window_tasks


def active_results(run_id):
    root = PROJECT / 'runs' / run_id
    if not (root / 'active.json').exists():
        return {}
    selection = json.loads((root / 'active.json').read_text())['selection']
    return {task_id: json.loads((root / 'versions' / (result_id + '.json')).read_text())
            for task_id, result_id in selection.items()}


def audit_run(spec):
    root = PROJECT / 'runs' / spec['run_id']
    parent = active_results(spec['run_id'])
    if len(parent) != 10:
        raise ValueError('Expected ten completed parent results')
    calls = frames = summaries = 0
    for task in selected_tasks():
        tid = task['task_id']
        result = parent[tid]
        windows = window_tasks(task, spec['window_seconds'])
        child = root / 'windows' / tid
        active = json.loads((child / 'active.json').read_text())['selection']
        if result['caption_status'] != 'success' or len(result['windows']) != len(windows):
            raise ValueError(f'{tid}: incomplete parent result')
        if len(active) != len(windows):
            raise ValueError(f'{tid}: incomplete window run')
        for window, trace in zip(windows, result['windows']):
            record = json.loads((child / 'versions' / (active[window['task_id']] + '.json')).read_text())
            bundle = json.loads((child / 'inputs' / (record['input_id'] + '.json')).read_text())
            if record['caption_status'] != 'success' or record.get('finish_reason') != 'stop' or not record.get('caption_complete'):
                raise ValueError(f"{window['window_id']}: incomplete generation")
            if trace['result_id'] != record['result_id'] or trace['generated_caption'] != record['generated_caption']:
                raise ValueError(f"{window['window_id']}: stale parent trace")
            evidence = bundle['frames']
            if not evidence or len(evidence) != len({item['pts'] for item in evidence}):
                raise ValueError(f"{window['window_id']}: missing or duplicate frames")
            if any(not window['clip_start_time_s'] <= item['source_time_s'] < window['clip_end_time_s'] for item in evidence):
                raise ValueError(f"{window['window_id']}: frame outside original boundary")
            if bundle['context']['background']['mode'] != 'none' or bundle['context']['history']['status'] != 'disabled':
                raise ValueError(f"{window['window_id']}: unexpected annotation or history")
            request = bundle['request']
            if request['input_mode'] != 'video' or request['do_sample_frames'] or request['do_resize']:
                raise ValueError(f"{window['window_id']}: processor changed visual sampling")
            calls += 1
            frames += len(evidence)
        if len(windows) > 1:
            detail = result.get('summary_usage') or {}
            if result.get('summary_method') != 'same_model_text_only' or detail.get('finish_reason') != 'stop' or not detail.get('caption_complete'):
                raise ValueError(f'{tid}: incomplete summary')
            calls += 1
            summaries += 1
        elif result['generated_caption'] != result['windows'][0]['generated_caption']:
            raise ValueError(f'{tid}: single window was rewritten')
    if (calls, frames, summaries) != (22, 123, 5):
        raise ValueError('Unexpected v3 call, frame or summary count')
    return {'parent_results': 10, 'window_results': 17, 'summary_calls': summaries,
            'total_model_calls': calls, 'real_sampled_frames': frames,
            'status': 'technical_checks_passed', 'quality_status': 'requires_video_review'}


def build_report(spec):
    baseline = active_results(spec['baseline_run_id'])
    candidate = active_results(spec['run_id'])
    rows = []
    for task in selected_tasks():
        tid = task['task_id']
        old = baseline.get(tid, {})
        new = candidate.get(tid, {})
        expected_windows = window_tasks(task, spec['window_seconds'])
        windows = new.get('windows', [])
        if new.get('caption_status') == 'success':
            if len(windows) != len(expected_windows):
                raise ValueError(f'{tid}: window count mismatch')
            if new.get('summary_method') != ('single_window_passthrough' if len(windows) == 1 else 'same_model_text_only'):
                raise ValueError(f'{tid}: unexpected summary method')
            for actual, expected in zip(windows, expected_windows):
                if actual['window_id'] != expected['window_id'] or actual['source_interval_s'] != [expected['clip_start_time_s'], expected['clip_end_time_s']]:
                    raise ValueError(f'{tid}: window identity or boundary changed')
        peaks = [window.get('peak_gpu_allocated_bytes') or {} for window in windows]
        peaks.append((new.get('summary_usage') or {}).get('peak_gpu_allocated_bytes') or {})
        v3_peak = {gpu: max([int(peak.get(gpu, 0)) for peak in peaks])
                   for gpu in {gpu for peak in peaks for gpu in peak}}
        rows.append({'task_id': tid, 'sample_id': task['sample_id'],
                     'source_interval_s': [task['clip_start_time_s'], task['clip_end_time_s']],
                     'duration_s': task['clip_end_time_s'] - task['clip_start_time_s'],
                     'window_count': len(expected_windows),
                     'v21_result_id': old.get('result_id'),
                     'v21_status': old.get('caption_status', 'pending'),
                     'v21_caption': old.get('generated_caption', ''),
                     'v21_generation_seconds': old.get('generation_seconds'),
                     'v21_input_tokens': old.get('input_tokens'),
                     'v21_generated_tokens': old.get('generated_tokens'),
                     'v21_peak_gpu_allocated_bytes': old.get('peak_gpu_allocated_bytes'),
                     'v3_result_id': new.get('result_id'),
                     'v3_status': new.get('caption_status', 'pending'),
                     'v3_caption': new.get('generated_caption', ''),
                     'v3_windows': windows,
                     'v3_summary_method': new.get('summary_method'),
                     'v3_generation_seconds': new.get('generation_seconds'),
                     'v3_input_tokens': new.get('input_tokens'),
                     'v3_generated_tokens': new.get('generated_tokens'),
                     'v3_peak_gpu_allocated_bytes': v3_peak,
                     'review_action_order': '', 'review_repeated_cycles': '',
                     'review_final_state': '', 'review_unsupported_details': '',
                     'review_notes': ''})
    return rows


def write_report(spec, rows):
    folder = PROJECT / 'reports/experiments/v3_window_off'
    folder.mkdir(parents=True, exist_ok=True)
    atomic_json(folder / 'comparison.json', {'baseline_run_id': spec['baseline_run_id'],
                                             'v3_run_id': spec['run_id'], 'rows': rows})
    fields = [key for key in rows[0] if key != 'v3_windows']
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fields)
    writer.writeheader()
    writer.writerows({key: row[key] for key in fields} for row in rows)
    atomic_text(folder / 'review.csv', buffer.getvalue())
    lines = ['# v3 首片段窗口实验：与 v2.1 off 对照', '',
             '同一 camera2、Qwen 官方 off、2 fps、每帧 512000 像素及高清源视频。v3 使用独立的最多 5 秒窗口，再由同一模型汇总多窗口文本；没有标注背景或历史。',
             '窗口 Prompt 沿用六部分 r3 的事实约束，但修改了观察范围措辞；随机种子也按窗口 task_id 派生。质量差异不能严格单独归因于切分。',
             '其中五条片段不超过 5 秒，实际上没有被切开，只用于检查单窗口直接采用结果的链路；只有另外五条能检验跨窗口连续性与汇总。',
             '', '生成成功不表示事实准确；下表的动作顺序、重复周期、结尾状态和无依据细节均需观看连续视频后填写 review.csv。',
             '', '| 样本 | 窗口 | v2.1 | v3 |', '|---|---:|---|---|']
    for row in rows:
        lines.append(f"| {row['sample_id']} | {row['window_count']} | {row['v21_status']} | {row['v3_status']} |")
    if all(row['v21_status'] == row['v3_status'] == 'success' for row in rows):
        lines += ['', '## 资源对照', '',
                  '以下是各次模型生成阶段的合计；不含抽帧、输入准备和权重加载。多窗口分别调用模型，不能把合计当作端到端墙钟时间。', '',
                  '| 指标 | v2.1 整段 | v3 窗口＋汇总 |', '|---|---:|---:|']
        for field, label, format_value in [
            ('generation_seconds', '生成耗时合计', lambda n: f'{n:.1f} 秒'),
            ('input_tokens', '输入 token 合计', lambda n: str(int(n))),
            ('generated_tokens', '生成 token 合计', lambda n: str(int(n))),
        ]:
            old_total = sum(row['v21_' + field] or 0 for row in rows)
            new_total = sum(row['v3_' + field] or 0 for row in rows)
            lines.append(f'| {label} | {format_value(old_total)} | {format_value(new_total)} |')
    lines += ['', '## 优先观看的差异', '',
              '以下仅依据两版文字找出冲突，尚未用连续视频裁定正误：', '',
              '- sample_01：v2.1 提到衣架从晾衣架取下并向床边移动；v3 汇总没有保留向床边移动，且把衣架位置写得更确定。检查第二窗口与汇总是否遗漏末段。',
              '- sample_04：v2.1 写折叠被褥，v3 写将被褥展开；需要按视频前后状态确认方向。',
              '- sample_08：v2.1 写多次抖展并放下，v3 写最后折半；检查是否真实发生折叠，以及汇总有没有把连续的提起与放下误写成不同动作。',
              '- sample_09：两版都描述接头靠近后分开；检查窗口之间是否将同一根线误认成两根，以及最后分离是否可见。',
              '- sample_10：v3 写“完成了包裹调整”，单窗口结果对此结尾较确定；检查末帧是否足以证明完成。', '']
    for row in rows:
        lines += ['', f"## {row['task_id']}", '',
                  f"源时间：{row['source_interval_s'][0]}–{row['source_interval_s'][1]} 秒；{row['window_count']} 个窗口。", '',
                  '**v2.1 整段 caption：** ' + (row['v21_caption'] or '待生成'), '',
                  '**v3 最终 caption：** ' + (row['v3_caption'] or '待生成'), '']
        for window in row['v3_windows']:
            lines.append(f"- {window['source_interval_s'][0]}–{window['source_interval_s'][1]} 秒：{window['generated_caption']}")
    atomic_text(folder / 'comparison.md', '\n'.join(lines) + '\n')
    print(f"v3 {sum(row['v3_status'] == 'success' for row in rows)}/10; review: {folder / 'comparison.md'}")


if __name__ == '__main__':
    spec = json.loads(SPEC_PATH.read_text())
    folder = PROJECT / 'reports/experiments/v3_window_off'
    folder.mkdir(parents=True, exist_ok=True)
    atomic_json(folder / 'technical-audit.json', audit_run(spec))
    write_report(spec, build_report(spec))
