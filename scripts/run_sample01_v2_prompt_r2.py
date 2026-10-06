"""Sample01 camera2 6fps v2. Default prepares one task without inference.

--apply generates; --limit 24 --max-calls 24 covers the full sample.
Configuration changes require a new run ID. No API or cloud operations.
"""
import json
import os
import sys
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[1]
if __name__ == '__main__':
    config = json.loads((PROJECT / 'configs/sample01_v2_prompt_r2.json').read_text())
    if config.get('retired'):
        raise SystemExit('该中间版本已退役；后续以视频+r3基线做独立实验。')
    os.environ.setdefault('OMP_NUM_THREADS', str(config['cpu_threads']))
    os.environ.setdefault('MKL_NUM_THREADS', str(config['cpu_threads']))
    sys.path.insert(0, str(PROJECT / 'src'))
    from caption_system.pipeline.run import main
    from caption_system.data.tasks import read_jsonl
    tasks = [t for t in read_jsonl(PROJECT / 'metadata/tasks.jsonl') if t['sample_id'] == config['sample'] and t['camera_id'] == config['camera']]
    if len(tasks) != config['expected_tasks'] or len({t['clip_id'] for t in tasks}) != config['expected_clips']:
        raise ValueError('Sample task domain differs from the fixed baseline configuration')
    if {t['camera_id'] for t in tasks} != {config['camera']}:
        raise ValueError('Baseline requires the configured camera')
    args = ['caption.py', '--run', config['run_id'], '--prompt-id', config['prompt_id'],
            '--provider', config['provider'], '--sample', config['sample'], '--camera', config['camera'], '--sampling-fps', str(config['sampling_fps']),
            '--prompt', str(PROJECT / config['prompt_file']), '--background', 'none',
            '--limit', '1', '--max-calls', '1']
    for key in ['frames', 'max_pixels', 'max_new_tokens', 'max_request_bytes', 'max_deviation_s']:
        args.extend(['--' + key.replace('_', '-'), str(config[key])])
    sys.argv = args + sys.argv[1:]
    main()
