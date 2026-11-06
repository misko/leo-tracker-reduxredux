"""Retain complete native parity and separately measured grid timing evidence."""

import argparse
import hashlib
import json
import shutil
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    pair, bench = args.pair, args.benchmark
    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    parity = read(bench / 'parity.json')
    assert parity['profile_science_and_eight_pngs_exact']
    for plan in (read(pair / 'plan.json'), read(bench / 'plan.json')):
        for name, sha in plan['bindings'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    trials = read(bench / 'trials.json')
    assert len(trials) == 6 and all(r['exact'] and r['completed'] for r in trials)
    tests = 0
    for name in ('tests-broad.xml', 'benchmark-tests.xml'):
        suites = list(ET.parse(pair / name).getroot().iter('testsuite'))
        assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
        tests += sum(int(s.attrib['tests']) for s in suites)
    means = {side: dict(
        seconds=statistics.mean(r['seconds'] for r in trials if r['name'] == side),
        cpu_seconds=statistics.mean(r['self_cpu_seconds'] + r['children_cpu_seconds']
                                    for r in trials if r['name'] == side))
        for side in ('baseline', 'candidate')}
    stages = {}
    for side in ('baseline', 'candidate'):
        supervisor = read(pair / side / 'attempt/supervisor.json')
        assert supervisor['returncode'] == 0 and supervisor['worker']['status'] == 'complete'
        assert not supervisor['worker']['resumed']
        stages[side] = {r['stage']: r['seconds'] for line in
                        (pair / side / 'attempt/worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
    for source, destination, names in (
        (pair, 'native', ['plan.json', 'comparison.json', 'baseline-sources.json',
                          'candidate-sources.json', 'baseline-process-time.txt',
                          'candidate-process-time.txt', 'baseline-resources-start.json',
                          'baseline-resources-end.json', 'candidate-resources-start.json',
                          'candidate-resources-end.json', 'tests.xml', 'tests-final.xml',
                          'tests-broad.xml', 'benchmark-tests.xml']),
        (bench, 'benchmark', ['plan.json', 'trials.json', 'parity.json', 'supervisor.json',
                              'worker.json', 'resources-start.json', 'resources-end.json',
                              'reference.py'])):
        dest = out / destination
        dest.mkdir(exist_ok=True)
        for name in names:
            shutil.copyfile(source / name, dest / name)
    shutil.copyfile(pair / 'job-tests.xml', out / 'native/job-tests.xml')
    for side in ('baseline', 'candidate'):
        for name in read(pair / f'{side}-sources.json'):
            dest = out / 'measured' / side / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pair / f'{side}-src' / name, dest)
    for side in stages:
        shutil.copyfile(pair / side / 'attempt/supervisor.json', out / 'native' / f'{side}.json')
        shutil.copyfile(pair / side / 'isolation.json', out / 'native' / f'{side}-isolation.json')
    (out / 'native/stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    summary = dict(scan='DS26-0002', tests=tests, exact=True,
                   process_seconds=comparison['observed_process_seconds'],
                   plot_stage_seconds={side: stages[side]['plot_evidence'] for side in stages},
                   grid_benchmark=means, grid_trials=6, grid_points=trials[0]['grid_points'],
                   production_modified=False, full_ds26_qualified=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    colors = ['#8796a5', '#32846b']
    names = ['Serial grid', '3 grid batches']
    values = [[comparison['observed_process_seconds'][s] for s in ('baseline', 'optimized')],
              [stages[s]['plot_evidence'] for s in ('baseline', 'candidate')],
              [means[s]['seconds'] for s in ('baseline', 'candidate')]]
    titles = ['Complete native run\nShared-host timing; one pair',
              'Grid + plot evidence stage\nWithin those native runs',
              'Isolated grid: three alternating pairs\nPrepared live context; exact scores']
    for ax, vals, title in zip(axes, values, titles, strict=True):
        bars = ax.bar(names, vals, color=colors)
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=title, ylabel='Wall seconds', ylim=(0, max(vals) * 1.22))
        ax.tick_params(axis='x', labelrotation=12)
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4), layout='constrained')
    x = np.arange(3)
    for offset, side, color in zip((-.18, .18), ('baseline', 'candidate'), colors, strict=True):
        vals = [r['seconds'] for r in trials if r['name'] == side]
        ax.bar(x + offset, vals, width=.36, label=side, color=color)
    ax.set(xticks=x, xticklabels=['AB', 'BA', 'AB'], ylabel='Grid wall seconds',
           title='DS26-0002 · complete grid in each trial · both c arms exact')
    ax.legend()
    fig.savefig(out / 'grid-trials.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
