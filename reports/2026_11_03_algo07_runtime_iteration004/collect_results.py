"""Seal cache qualification and the independently measured native GLRT profile."""

import hashlib
import json
import pstats
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from compare_algo07_runtime_replays import compare
from stage_algo07_runtime import PREPARED_FILES

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = Path('/srv/bulk/leo/research/algo07-runtime-20261103')
BASE = Path('/opt/leo-fast-graph/7cafccaced18e6b0fa9266bd18339d61f0f9c1f4')


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    shutil.copyfile(source, target)


def metrics(folder):
    timing = read(folder/'timing.json')
    summary = read(folder/'results/summary.json')
    stats = pstats.Stats(str(folder/'profile.pstats')).stats
    bound = next(v for k, v in stats.items() if k[2] == 'hierarchical_bound')
    return dict(wall_seconds=timing['wall_seconds'],
                cpu_seconds=timing['user_cpu_seconds']+timing['system_cpu_seconds'],
                peak_rss_kib=timing['peak_child_rss_kib'],
                orchestration_seconds=summary['seconds'], kernel_seconds=summary['kernel_seconds'],
                curved_evaluations=bound[1], curved_seconds=bound[3])


def main():
    rows = []
    for case, baseline in [('fresh-fallback', 'replay-prepared-geometry'),
                           ('slow-additive', 'replay-calibration-control-r2')]:
        trials = ['replay-calibration-cache', 'replay-calibration-cache1',
                  'replay-calibration-cache1-r2']
        if case == 'slow-additive':
            trials.append(baseline)
        for trial in trials:
            source, target = DATA/case/trial, OUT/case/trial
            for name in ('timing.json', 'launch.json', 'read-audit.json',
                         'profile.pstats', 'results/summary.json'):
                copy(source/name, target/name)
            for path in (source/'results/SCAN').rglob('*.json'):
                copy(path, target/path.relative_to(source))
            parity = compare(DATA/case/baseline/'results', source/'results')
            assert parity['passed'] and parity['differing_floats'] == 0
            write(OUT/case/(trial+'-parity.json'), parity)
            timing = read(source/'timing.json')
            audit = read(source/'read-audit.json')
            assert audit['verified'] and timing['reference_after']['verified']
            assert timing['successful_execution'] and timing['manifest_unchanged']
        candidate = ('replay-calibration-cache1' if case == 'fresh-fallback'
                     else 'replay-calibration-cache1-r2')
        source = DATA/case/candidate
        rows.append(dict(case=case, baseline_trial=baseline, candidate_trial=source.name,
                         baseline=metrics(DATA/case/baseline), candidate=metrics(source),
                         cache8_prototype=metrics(DATA/case/'replay-calibration-cache'),
                         first_cache1=metrics(DATA/case/'replay-calibration-cache1'),
                         repeated_cache1=metrics(DATA/case/'replay-calibration-cache1-r2'),
                         parity=compare(DATA/case/baseline/'results', source/'results'),
                         read_audit_verified=True, frozen_inputs_verified=True))
    write(OUT/'full-replays.json', dict(passed=True, cases=rows,
                                       scope='Complete prepared ALGO07 workers, both arms'))
    population = read(DATA/'population/calibration-cache1-parity.json')
    assert population['passed'] and len(population['results']) == 16
    copy(DATA/'population/calibration-cache1-parity.json', OUT/'population-parity.json')
    for item in population['results']:
        source = Path(item['root'])/'calibration-cache1'
        target = OUT/'population'/item['case']
        for name in ('timing.json', 'launch.json', 'read-audit.json', 'results/summary.json'):
            copy(source/name, target/name)
        write(target/'captured-values-sha256.json', {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((source/'results').glob('call-*'))})
    baseline = read(BASE/'release-manifest.json')['files_sha256']
    write(OUT/'implementation.json', dict(
        default_cache_size=1,
        files_sha256={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                      for p in PREPARED_FILES},
        baseline_files_sha256={p: baseline.get(p) for p in PREPARED_FILES},
        scientific_policy_changed=False))
    glrt = DATA/'glrt-native-lower'
    for name in ('input.json', 'frozen.json', 'baseline/timing.json', 'baseline/launch.json',
                 'baseline/profile.pstats', 'baseline/result.json'):
        copy(glrt/name, OUT/'native-glrt'/name)
    result = read(glrt/'baseline/result.json')
    assert result['published_candidates_exact'] and result['window_count'] == 16
    stats = pstats.Stats(str(glrt/'baseline/profile.pstats')).stats
    coarse = sum(v[2] for k, v in stats.items()
                 if '_native_acquisition.folded_anchor_score_grid' in k[2])
    write(OUT/'native-glrt/hotspots.json', dict(
        coarse_acquisition_seconds=coarse, detector_seconds=result['total_detector_seconds'],
        fraction=coarse/result['total_detector_seconds'], windows=16,
        published_candidates_exact=True, full_scan_replayed=False))
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), constrained_layout=True)
    labels = ['Prepared geometry', 'Eight-position cache', 'One-position cache']
    for ax, row in zip(axes, rows, strict=True):
        values = [row[k]['wall_seconds'] for k in ('baseline', 'cache8_prototype', 'candidate')]
        bars = ax.bar(range(3), values, color=['#526b8e', '#a9a9a9', '#189a94'])
        ax.bar_label(bars, labels=[f'{v:.1f}s' for v in values], padding=4)
        ax.set_xticks(range(3), labels, rotation=12, ha='right')
        ax.set_ylim(0, max(values)*1.2)
        ax.set_ylabel('Complete ALGO07 worker wall seconds')
        ax.set_title(row['case'])
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('Exact scientific parity; bounded one-position reuse selected')
    fig.savefig(OUT/'worker_runtime.png', dpi=170)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(7, 4), constrained_layout=True)
    parts = [coarse, result['total_detector_seconds']-coarse]
    bars = ax.barh(['Native coarse acquisition', 'Remaining detector work'], parts,
                   color=['#d67240', '#526b8e'])
    ax.bar_label(bars, labels=[f'{v:.2f}s' for v in parts], padding=4)
    ax.set_xlim(0, max(parts)*1.2)
    ax.set_xlabel('Profiled seconds across 16 paired-receiver windows')
    ax.set_title('Production 10 MS/s GLRT: all eight channels')
    fig.savefig(OUT/'native_glrt_hotspot.png', dpi=170)
    plt.close(fig)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
