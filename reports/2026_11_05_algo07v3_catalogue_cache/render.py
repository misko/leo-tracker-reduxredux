"""Validate source-bound preparation trials and complete native publication."""

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_files(source, dest, names):
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(source / name, dest / name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--benchmarks', type=Path, nargs=2, required=True)
    args = parser.parse_args()
    pair, out = args.pair, Path(__file__).resolve().parent
    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    assert len(comparison['source_changes']) == 3 and not comparison['added_modules']
    for name, sha in read(pair / 'plan.json')['bindings'].items():
        assert digest(Path(name)) == sha, name
    baseline = read(pair / 'baseline-sources.json')
    old = {str(Path('src', n).resolve()): pair / 'baseline-src' / n for n in baseline}
    summaries, trials = {}, {}
    for scan, bench in zip(('DS26-0002', 'DS26-0066'), args.benchmarks, strict=True):
        bindings = read(bench / 'plan.json')['bindings']
        old[str(Path('tools/probe_algo07v3_catalogue_cache.py').resolve())] = (
            bench / 'measured-probe.py')
        for name, sha in bindings.items():
            assert digest(old.get(name, Path(name))) == sha, name
        result, rows = read(bench / 'summary.json'), read(bench / 'trials.json')
        assert result['exact'] and result['executions'] == len(rows) == 6
        assert all(r['exact'] for r in rows) and not result['full_pipeline_speed_benchmark']
        for row in rows:
            assert row['cache_after_recovery']['evictions'] == 0
            assert row['cache_after_recovery']['misses'] == row['cache_after_initial']['misses']
            hits = row['cache_after_recovery']['hits'] - row['cache_after_initial']['hits']
            assert hits == (row['snapshots'] if row['side'] == 'candidate' else 0)
        result['expected_fingerprint_sha256'] = digest(bench / 'expected.json')
        summaries[scan], trials[scan] = result, rows
        dest = out / 'benchmarks' / scan
        copy_files(bench, dest, ['plan.json', 'summary.json', 'trials.json',
                                 'resources-start.json', 'resources-end.json', 'measured-probe.py'])
        (dest / 'fingerprint-sha256.txt').write_text(result['expected_fingerprint_sha256'] + '\n')
    suites = list(ET.parse(pair / 'tests-broad.xml').getroot().iter('testsuite'))
    tests = sum(int(s.attrib['tests']) for s in suites)
    assert tests == 722 and not any(int(s.attrib[k]) for s in suites
                                  for k in ('errors', 'failures', 'skipped'))
    stages = {}
    for side in ('baseline', 'candidate'):
        outcome = read(pair / side / 'attempt/supervisor.json')
        assert outcome['returncode'] == 0 and outcome['worker']['status'] == 'complete'
        assert not outcome['worker']['resumed']
        stages[side] = {r['stage']: r['seconds'] for line in
                        (pair / side / 'attempt/worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
    copy_files(pair, out / 'native', [
        'plan.json', 'comparison.json', 'baseline-sources.json', 'candidate-sources.json',
        'tests-focused.xml', 'tests-broad.xml', 'baseline-process-time.txt',
        'candidate-process-time.txt', 'baseline-resources-start.json',
        'baseline-resources-end.json', 'candidate-resources-start.json',
        'candidate-resources-end.json'])
    for side in stages:
        for name in baseline:
            dest = out / 'measured' / side / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pair / (side + '-src') / name, dest)
        shutil.copyfile(pair / side / 'attempt/supervisor.json', out / 'native' / (side + '.json'))
        shutil.copyfile(pair / side / 'isolation.json', out / 'native' / (side + '-isolation.json'))
    (out / 'native/stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    summary = dict(native_scan='DS26-0002', exact_science_and_eight_pngs=True, tests=tests,
                   native_seconds=comparison['observed_process_seconds'],
                   catalogue_seconds={s: stages[s]['recovery_catalogue'] for s in stages},
                   preparation_trials=summaries, runtime_integrated=True,
                   production_modified=False, full_ds26_qualified=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    colors = ['#8796a5', '#32846b']
    labels = ['Uncached recovery', 'Reuse validated text']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    values = [[summary['native_seconds'][s] for s in ('baseline', 'optimized')]]
    values += [[summaries[scan]['means'][s]['recovery_seconds'] for s in ('baseline', 'candidate')]
               for scan in summaries]
    titles = ['Complete native DS26-0002\nOne pair; shared-host observation'] + [
        scan + ' catalogue\nMean of three alternating pairs' for scan in summaries]
    for ax, vals, title in zip(axes, values, titles, strict=True):
        bars = ax.bar(labels, vals, color=colors)
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=title, ylabel='Wall seconds', ylim=(0, max(vals) * 1.22))
        ax.tick_params(axis='x', labelrotation=20)
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    for ax, (scan, rows) in zip(axes, trials.items(), strict=True):
        for offset, side, color in zip((-.18, .18), ('baseline', 'candidate'), colors, strict=True):
            vals = [r['recovery_seconds'] for r in rows if r['side'] == side]
            ax.bar(np.arange(3) + offset, vals, width=.36, label=side, color=color)
        ax.set(xticks=np.arange(3), xticklabels=['AB', 'BA', 'AB'],
               ylabel='Catalogue wall seconds', title=scan + ' · complete preparation exact')
        ax.legend()
    fig.savefig(out / 'catalogue-trials.png', dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'preparation_trials'}, indent=2))


if __name__ == '__main__':
    main()
