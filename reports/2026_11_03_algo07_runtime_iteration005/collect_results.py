"""Collect every bounded GLRT trial and verify all receiver outputs exactly."""

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPORT = Path(__file__).resolve().parent
PRIVATE = Path('/srv/bulk/leo/research/algo07-runtime-20261103')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect():
    receipt = read(PRIVATE/'glrt-tiling-prototype/prototype-build.json')
    for label, root in [('original', receipt['base']), ('candidate', receipt['candidate'])]:
        for name, expected in receipt[label+'_sha256'].items():
            assert sha(Path(root)/name) == expected, name
    shutil.copyfile(PRIVATE/'glrt-tiling-prototype/prototype-build.json',
                    REPORT/'prototype-build.json')
    cases = [('Fresh lower', 'lower'), ('Fresh upper', 'upper')]
    cases += [(r['case'], r['case']) for r in read(REPORT/'cohort-selection.json')['rows']]
    rows = []
    for label, suffix in cases:
        fixture = PRIVATE/('glrt-native-'+suffix)
        destination = REPORT/suffix
        destination.mkdir(exist_ok=False)
        for name in ('input.json', 'frozen.json'):
            shutil.copyfile(fixture/name, destination/name)
        frozen = read(fixture/'frozen.json')
        assert all(sha(Path(r['path'])) == r['sha256'] for r in frozen['files'])
        baseline = read(fixture/'baseline/result.json')
        trials = {}
        for name in ('baseline', 'tiling-candidate', 'baseline-r2', 'tiling-candidate-r2'):
            source = fixture/name
            if not source.exists():
                continue
            result, timing = read(source/'result.json'), read(source/'timing.json')
            assert timing['successful_execution'] and timing['reference_after']['verified']
            assert timing['manifest_unchanged'] and result['published_candidates_exact']
            assert len(result['windows']) == len(baseline['windows']) == 16
            for a, b in zip(baseline['windows'], result['windows'], strict=True):
                assert a['visit'] == b['visit'] and a['channel'] == b['channel']
                assert a['receivers'] == b['receivers'], (label, name, a['visit'])
            (destination/name).mkdir()
            for item in ('result.json', 'timing.json', 'launch.json', 'profile.pstats'):
                shutil.copyfile(source/item, destination/name/item)
            trials[name] = dict(detector_seconds=result['total_detector_seconds'],
                                wall_seconds=timing['wall_seconds'],
                                peak_child_rss_kib=timing['peak_child_rss_kib'],
                                all_receiver_outputs_exact=True,
                                reference_hashes_verified=True)
        rows.append(dict(case=label, windows=16, receivers=32, trials=trials,
                         speedup=trials['baseline']['detector_seconds']/
                                 trials['tiling-candidate']['detector_seconds']))
    result = dict(passed=True, unique_windows=sum(r['windows'] for r in rows),
                  receiver_outputs=sum(r['receivers'] for r in rows), cases=rows,
                  native_code_unchanged_since_build=True,
                  full_scan_replayed=False, localization_replayed=False,
                  production_glrt_changed=False)
    with (REPORT/'results.json').open('x') as stream:
        json.dump(result, stream, indent=2)
    fig, ax = plt.subplots(figsize=(10, 5))
    x = list(range(len(rows)))
    ax.bar([i-.18 for i in x], [r['trials']['baseline']['detector_seconds'] for r in rows],
           .36, label='Installed GLRT')
    ax.bar([i+.18 for i in x], [r['trials']['tiling-candidate']['detector_seconds'] for r in rows],
           .36, label='Isolated 12-lane tiling')
    ax.set_xticks(x, [r['case'] for r in rows])
    ax.set_ylabel('Detector time for 16 paired windows (seconds)')
    ax.set_title('Native 10 MS/s GLRT: exact receiver-output parity\n'
                 'Shared host; bounded fixtures, not full-scan latency')
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORT/'detector_runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(result))


if __name__ == '__main__':
    collect()
