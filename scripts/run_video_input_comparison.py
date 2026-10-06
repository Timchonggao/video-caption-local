"""Frozen-frame A/B/C/D experiment; no cloud operations or automatic expansion.

Default lists the plan. --phase prepare creates CPU inputs for B/C/D;
--phase b-pilot runs B's shortest/longest; b-rest/c/d run their five tasks.
Every inference phase requires --apply. Inputs and successful results resume.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CONFIG = PROJECT / 'configs/video_input_comparison.json'


def command(config, group, phase):
    spec = config['groups'][group]
    args = [sys.executable, str(PROJECT / 'scripts/caption.py'), '--run', spec['run_id'],
            '--provider', 'qwen', '--sample', config['sample'], '--camera', config['camera'],
            '--prompt-id', 'baseline-v2', '--prompt', str(PROJECT / spec['prompt_file']),
            '--input-mode', spec['input_mode'], '--evidence-run', config['evidence_run'],
            '--comparison-group', group, '--background', 'none', '--stop-on-error',
            '--limit', '5', '--max-calls', '5']
    for key in ['frames', 'sampling_fps', 'frame_max_pixels', 'max_new_tokens', 'max_request_bytes', 'max_deviation_s']:
        args.extend(['--' + key.replace('_', '-'), str(config[key])])
    for task in config['task_ids']:
        args.extend(['--experiment-task-id', task])
    if phase == 'b-pilot':
        for task in ['sample_01_seg02_sub10__camera2', 'sample_01_seg02_sub12__camera2']:
            args.extend(['--task-id', task])
    return args


def validate_prepared(config, group):
    spec = config['groups'][group]
    folder = PROJECT / 'runs' / spec['run_id']
    preview = json.loads((folder / 'preview.json').read_text())
    entries = {p['task_id']: p for p in preview['inputs']}
    if set(entries) != set(config['task_ids']) or not all(p.get('ready') for p in entries.values()):
        raise ValueError(f'{group}: incomplete or failed CPU preparation')
    expected = dict(zip(config['task_ids'], [42, 30, 9, 54, 75]))
    for task, entry in entries.items():
        bundle = json.loads((folder / entry['path']).read_text())
        if len(bundle['frames']) != expected[task]:
            raise ValueError('Frozen frame count changed')
        if bundle['request']['image_sizes'] != [[768, 640]] * expected[task]:
            raise ValueError('Frame precision differs from A')
        if bundle['request']['request_bytes'] > config['max_request_bytes']:
            raise ValueError('Input exceeds budget')
        if spec['input_mode'] == 'video':
            timing = bundle['request']['temporal_evidence']
            if timing['real_frame_count'] != expected[task] or timing['padding_count'] != expected[task] % 2:
                raise ValueError('Invalid video padding')
    print(f'{group}: five frozen inputs verified', flush=True)


def validate_results(config, group, phase):
    folder = PROJECT / 'runs' / config['groups'][group]['run_id']
    selection = json.loads((folder / 'active.json').read_text())['selection']
    wanted = (['sample_01_seg02_sub10__camera2','sample_01_seg02_sub12__camera2']
              if phase == 'b-pilot' else config['task_ids'])
    for task in wanted:
        result = json.loads((folder / 'versions' / (selection[task] + '.json')).read_text())
        if result['caption_status'] != 'success' or result.get('finish_reason') != 'stop':
            raise ValueError(f'{group}: result failed/truncated; no automatic fallback')
    print(f'{group}: {len(wanted)} successful results verified', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['plan', 'prepare', 'b-pilot', 'b-rest', 'c', 'd'], default='plan')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text())
    if config.get('retired'):
        raise SystemExit('四组探索已收敛并清理；保留视频+r3，后续请使用独立 thinking 实验，不重建中间组。')
    for group, spec in config['groups'].items():
        print(f'{group}: {spec["run_id"]}; {spec["input_mode"]}; five tasks', flush=True)
    if args.phase == 'plan':
        print('A reused; B/C/D add 15 calls. Stop for human review; no cloud.')
        return
    if args.phase != 'prepare' and not args.apply:
        parser.error('Inference requires --apply')
    env = dict(os.environ)
    env['OMP_NUM_THREADS'] = env['MKL_NUM_THREADS'] = str(config['cpu_threads'])
    groups = ['B', 'C', 'D'] if args.phase == 'prepare' else [{'b-pilot':'B','b-rest':'B','c':'C','d':'D'}[args.phase]]
    for group in groups:
        cmd = command(config, group, args.phase)
        if args.phase != 'prepare':
            if args.phase == 'b-rest':
                validate_results(config, 'B', 'b-pilot')
            cmd.append('--apply')
        subprocess.run(cmd, env=env, cwd=PROJECT, check=True)
        if args.phase == 'prepare':
            validate_prepared(config, group)
        else:
            validate_results(config, group, args.phase)

if __name__ == '__main__':
    main()
