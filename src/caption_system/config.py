"""Resolve configured CFS paths without depending on the caller's working directory."""
import json, os
from pathlib import Path
PROJECT = Path(__file__).resolve().parents[2]
PATHS = json.loads((PROJECT / 'configs/paths.json').read_text())
for name in PATHS:
    PATHS[name] = os.environ.get('CAPTION_' + name.upper(), PATHS[name])
VERSION = 'mcap-v2'
