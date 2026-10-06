import sys, runpy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
runpy.run_module('caption_system.video.validate_media', run_name='__main__')
