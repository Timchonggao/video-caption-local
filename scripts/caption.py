"""Single entry point; safe dry-run for inference unless --apply is given."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from caption_system.pipeline.run import main
if __name__ == '__main__':
    main()
