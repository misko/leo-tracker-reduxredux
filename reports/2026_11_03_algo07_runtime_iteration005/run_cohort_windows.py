"""Sample one eligible scan per frozen cohort, then replay paired GLRT windows."""

import gzip
import hashlib
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = Path(__file__).resolve().parent
PRIVATE = Path('/srv/bulk/leo/research/algo07-runtime-20261103')
BASE = Path('/opt/leo-standard-fast/17bf8ccfa3dd495f040fcb05fbcffcb1e11c42e3/native-worker')
CANDIDATE = PRIVATE/'glrt-tiling-prototype'
SEED = 20261103


def selection():
    sources = {
        'DS26': 'reports/2026_10_30_ds26_all_new_recordings/manifest.json.gz',
        'DS27': 'reports/2026_10_31_ds27_algo04_review/dataset/manifest.json.gz',
        'DS28': '/home/mouse9911/gits/leo-tracker-reduxredux/reports/'
                '2026_11_01_ds28_revision2/dataset/manifest.json.gz',
    }
    rows = []
    for dataset, name in sources.items():
        data = (Path(name).read_bytes() if Path(name).is_absolute() else
                subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:'+name]))
        document = json.loads(gzip.decompress(data))
        eligible = sorted((m for m in document['members']
                           if m.get('tracking_inputs') and m.get('sample_rate_hz') == 10000000),
                          key=lambda m: m['dataset_label'])
        member = random.Random(SEED).choice(eligible)
        rows.append(dict(dataset=dataset, dataset_revision=document.get('revision'),
                         source=name, source_sha256=hashlib.sha256(data).hexdigest(),
                         eligible=len(eligible), case=member['dataset_label'],
                         recording=member['recording_id'],
                         run_id=Path(member['tracking_inputs'][0]['path']).stem))
    result = dict(seed=SEED, selection='one random published 10 MS/s scan per cohort; '
                  'no localization or signal score used', rows=rows,
                  window_selection='two random whole paired-receiver windows per channel',
                  published_fields_required='exact equality; no tolerance',
                  scope='bounded native GLRT evidence, not whole-scan localization validation')
    with (REPORT/'cohort-selection.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    return rows


if __name__ == '__main__':
    rows = selection()
    for i, row in enumerate(rows):
        fixture = PRIVATE/('glrt-native-'+row['case'])
        tool = ROOT/'tools/profile_algo07_glrt.py'
        commands = [[sys.executable, '-B', str(tool), 'snapshot', '--bulk-root',
                     '/srv/bulk/leo', '--run-id', row['run_id'], '--source-root', str(BASE),
                     '--output', str(fixture), '--per-channel', '2', '--seed', str(SEED)]]
        variants = [('baseline', BASE), ('tiling-candidate', CANDIDATE)]
        if i % 2:
            variants.reverse()
        commands += [[sys.executable, '-B', str(tool), 'run', '--snapshot', str(fixture),
                      '--source-root', str(source), '--output', str(fixture/name),
                      '--timeout', '300'] for name, source in variants]
        for command in commands:
            print(json.dumps(dict(case=row['case'], command=command)), flush=True)
            subprocess.run(command, check=True, timeout=360, cwd=ROOT)
