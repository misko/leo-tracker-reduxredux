"""Collect immutable experiment receipts and render the worker comparison."""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from compare_algo07_runtime_replays import compare

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
DATA = Path('/srv/bulk/leo/research/algo07-runtime-20261103')
PAIRS = (
    ('fresh-fallback', 'replay-current', 'replay-prepared-geometry', 'Single-family case'),
    ('slow-additive', 'replay-contractions', 'replay-prepared-geometry',
     'Two-family case: first pair'),
    ('slow-additive', 'replay-geometry-control-r2', 'replay-prepared-geometry-r2',
     'Two-family case: concurrent repeat'),
)


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


def one(case, trial):
    source = DATA/case/trial
    target = OUT/case/trial
    for name in ('timing.json', 'launch.json', 'read-audit.json',
                 'profile.pstats', 'results/summary.json'):
        copy(source/name, target/name)
    for path in (source/'results/SCAN').rglob('*.json'):
        copy(path, target/path.relative_to(source))
    timing = read(source/'timing.json')
    summary = read(source/'results/summary.json')
    audit = read(source/'read-audit.json')
    assert timing['successful_execution'] and timing['reference_after']['verified']
    assert timing['manifest_unchanged'] and audit['verified']
    return dict(trial=trial, wall_seconds=timing['wall_seconds'],
                cpu_seconds=timing['user_cpu_seconds']+timing['system_cpu_seconds'],
                peak_rss_kib=timing['peak_child_rss_kib'],
                orchestration_seconds=summary['seconds'], kernel_seconds=summary['kernel_seconds'],
                kernel_calls=len(summary['kernel_calls']), read_audit_verified=True,
                frozen_files_verified=timing['reference_after']['files'])


def main():
    rows = []
    for case, baseline, candidate, label in PAIRS:
        a, b = one(case, baseline), one(case, candidate)
        result = compare(DATA/case/baseline/'results', DATA/case/candidate/'results')
        # This iteration requires exact parity, stricter than the shared comparator.
        assert result['passed'] and result['differing_floats'] == 0
        write(OUT/case/(candidate+'-parity.json'), result)
        rows.append(dict(case=case, label=label, baseline=a, candidate=b,
                         speedup=a['wall_seconds']/b['wall_seconds'],
                         exact_scientific_leaves=result['exact_leaves']))
    for case in ('fresh-fallback', 'slow-additive'):
        for name in ('source.json', 'frozen.json'):
            copy(DATA/case/name, OUT/case/name)
    population = read(DATA/'population/prepared-geometry-parity.json')
    assert population['passed'] and len(population['results']) == 16
    copy(DATA/'population/prepared-geometry-parity.json', OUT/'population-parity.json')
    for item in population['results']:
        source = Path(item['root'])/'prepared-geometry'
        target = OUT/'population'/item['case']
        for name in ('timing.json', 'launch.json', 'read-audit.json', 'results/summary.json'):
            copy(source/name, target/name)
        write(target/'captured-values-sha256.json', {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((source/'results').glob('call-*'))
        })
    copy(DATA/'compiled-factor-probe/result.json', OUT/'compiled-factor-probe.json')
    implementation = [
        'src/leo/analysis/research/continuous_curve_fit.py',
        'src/leo/analysis/research/orbit_uncertainty.py',
        'src/leo/analysis/research/prepared_phase_geometry.py',
        'tools/predictive_new_family.py', 'tools/probe_joint_predictive_families.py',
        'tests/analysis/test_prepared_phase_geometry.py',
    ]
    write(OUT/'implementation.json', dict(
        baseline_commit=subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        file_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                     for name in implementation},
        deployment='Not deployed; existing iteration 002 runtime remains installed',
    ))
    write(OUT/'comparison.json', dict(
        pairs=rows, scope='Complete prepared ALGO07 worker; excludes upstream stages',
        scientific_values_exact=True, all_pairs_faster=all(r['speedup'] > 1 for r in rows)))
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), constrained_layout=True)
    for ax, row in zip(axes, rows, strict=True):
        values = [row[key]['wall_seconds'] for key in ('baseline', 'candidate')]
        bars = ax.bar(['Current runtime', 'Prepared geometry'], values,
                      color=['#526b8e', '#189a94'])
        ax.bar_label(bars, labels=[f'{v:.1f} s' for v in values], padding=4)
        ax.set_ylim(0, max(values)*1.2)
        ax.set_title(row['label'], fontsize=11)
        ax.set_ylabel('ALGO07 worker wall time (seconds)')
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    fig.suptitle('Iteration 003: exact scientific parity; mixed timing evidence')
    fig.savefig(OUT/'worker_runtime.png', dpi=170)
    plt.close(fig)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
