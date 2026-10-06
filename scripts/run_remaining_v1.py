"""Run the same pure-visual v1 on samples 02–10; default is a plan only.

--apply executes sequentially in distinct, resumable runs. Existing sample01
results are preserved. No cloud operations or closed API calls.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', action='append', choices=[f'sample_{i:02d}' for i in range(2, 11)])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    config = json.loads((PROJECT / 'configs/sample01_v1.json').read_text())
    tasks = [json.loads(line) for line in (PROJECT / 'metadata/tasks.jsonl').read_text().splitlines() if line.strip()]
    samples = args.sample or [f'sample_{i:02d}' for i in range(2, 11)]
    if len(samples) != len(set(samples)):
        parser.error('Duplicate sample selection')
    env = dict(os.environ)
    env['OMP_NUM_THREADS'] = env['MKL_NUM_THREADS'] = str(config['cpu_threads'])
    total = 0
    commands = []
    for sample in samples:
        selected = [t for t in tasks if t['sample_id'] == sample]
        clips = {t['clip_id'] for t in selected}
        if not clips or len(selected) != len(clips) * 6 or len({t['task_id'] for t in selected}) != len(selected):
            raise ValueError(f'Invalid six-camera task domain: {sample}')
        for clip in clips:
            if {t['camera_id'] for t in selected if t['clip_id'] == clip} != {f'camera{i}' for i in range(6)}:
                raise ValueError(f'Missing camera: {clip}')
        run = f'qwen-{sample.replace("_", "")}-v1'
        cmd = [sys.executable, str(PROJECT / 'scripts/caption.py'), '--run', run,
               '--sample', sample, '--provider', config['provider'], '--prompt-id', config['prompt_id'],
               '--prompt', str(PROJECT / config['prompt_file']), '--background', 'none',
               '--limit', str(len(selected)), '--max-calls', str(len(selected)), '--apply']
        for key in ['frames', 'max_pixels', 'max_new_tokens', 'max_request_bytes', 'max_deviation_s']:
            cmd.extend(['--' + key.replace('_', '-'), str(config[key])])
        commands.append(cmd)
        total += len(selected)
        print(f'{sample}: {len(clips)} clips × 6 cameras = {len(selected)} tasks; run={run}', flush=True)
    print(f'Total: {total} tasks. Same v1 prompt, 12 frames/clip, no background/history/windows.', flush=True)
    if not args.apply:
        print('Plan only; add --apply to execute. No files or model calls created.')
        return
    for cmd in commands:
        subprocess.run(cmd, cwd=PROJECT, env=env, check=True)

if __name__ == '__main__':
    main()
