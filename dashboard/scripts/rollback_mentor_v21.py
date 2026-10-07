"""Restore the prior mentor presentation without deleting staged v2.1 data."""
import argparse
import json
from pathlib import Path

from cloud_api import query

VERSION = 'mcap-v2'
BACKUP = Path(__file__).resolve().parents[1] / '.local/cloud-sampling/mentor-v2_1/previous-publication.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Actually restore the presentation')
    args = parser.parse_args()
    previous = json.loads(BACKUP.read_text())
    rows = query('SELECT data FROM cs_dashboard WHERE version=?', [VERSION])['results']
    if len(rows) != 1:
        raise ValueError('Current publication missing')
    current = json.loads(rows[0]['data'])
    if current.get('presentation', {}).get('fixed_prompt_id') != 'baseline-v2-1':
        raise ValueError('Current presentation is not v2.1; refusing rollback')
    restored = {**current, 'presentation': previous['presentation'],
                'experiment': previous['experiment']}
    print('Restore presentation:', json.dumps(restored['presentation'], ensure_ascii=False))
    if args.apply:
        query('UPDATE cs_dashboard SET data=? WHERE version=?',
              [json.dumps(restored, ensure_ascii=False, sort_keys=True, separators=(',', ':')), VERSION])
        print('Prior mentor presentation restored; staged v2.1 records retained.')


if __name__ == '__main__':
    main()
