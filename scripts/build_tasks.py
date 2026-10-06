import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from caption_system.data.tasks import main
if __name__ == '__main__':
    main()
