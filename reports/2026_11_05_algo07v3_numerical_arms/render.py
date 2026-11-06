"""Verify native parity and original measured sources before exporting results."""

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


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    args = parser.parse_args()
    pair, bench = args.pair, args.benchmark
    out = Path(__file__).resolve().parent
    comparison = read(pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    parity = read(bench / 'parity.json')
    assert parity['profile_science_and_eight_pngs_exact']
    measurement = read(bench / 'benchmark.json')
    assert measurement['process']['returncode'] == 0
    assert measurement['worker']['status'] == 'complete' and not measurement['changed_sources']
    assert not measurement['full_pipeline_speed_benchmark']
    baseline = read(pair / 'baseline-sources.json')
    old_sources = {str(Path('src', n).resolve()): pair / 'baseline-src' / n for n in baseline}
    old_sources[str(Path('tools/probe_algo07v3_numerical_arms.py').resolve())] = (
        bench / 'measured-probe.py')
    for name, sha in read(bench / 'plan.json')['bindings'].items():
        assert digest(old_sources.get(name, Path(name))) == sha, name
    for name, sha in read(pair / 'plan.json')['bindings'].items():
        assert digest(Path(name)) == sha, name
    assert len(comparison['source_changes']) == 5 and not comparison['added_modules']
    suites = list(ET.parse(pair / 'tests-broad.xml').getroot().iter('testsuite'))
    tests = sum(int(s.attrib['tests']) for s in suites)
    assert tests == 716
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    records = read(bench / 'trials.json')
    assert len(records) == 1 and records[0]['kind'] == 'fit_new'
    assert records[0]['complete_result_and_receipt_exact']
    trials = records[0]['rows']
    assert len(trials) == 6 and all(r['completed'] and r['exact'] for r in trials)
    means = {side: dict(seconds=statistics.mean(r['seconds'] for r in trials if r['name'] == side),
                        cpu_seconds=statistics.mean(r['self_cpu_seconds'] +
                                                    r['children_cpu_seconds']
                                                    for r in trials if r['name'] == side))
             for side in ('baseline', 'candidate')}
    stages = {}
    for side in ('baseline', 'candidate'):
        outcome = read(pair / side / 'attempt/supervisor.json')
        assert outcome['returncode'] == 0 and outcome['worker']['status'] == 'complete'
        assert not outcome['worker']['resumed']
        stages[side] = {r['stage']: r['seconds'] for line in
                        (pair / side / 'attempt/worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
    for root, destination, names in (
        (pair, 'native', ['plan.json', 'comparison.json', 'baseline-sources.json',
                          'candidate-sources.json', 'tests-focused.xml', 'tests-broad.xml',
                          'baseline-process-time.txt', 'candidate-process-time.txt',
                          'baseline-resources-start.json', 'baseline-resources-end.json',
                          'candidate-resources-start.json', 'candidate-resources-end.json']),
        (bench, 'benchmark', ['plan.json', 'parity.json', 'trials.json', 'benchmark.json',
                              'resources-start.json', 'resources-end.json', 'measured-probe.py',
                              'fit_new-original.py', 'fit_new-candidate.py',
                              'fit_shared-original.py', 'fit_shared-candidate.py']),
    ):
        dest = out / destination
        dest.mkdir(exist_ok=True)
        for name in names:
            shutil.copyfile(root / name, dest / name)
    for side in stages:
        for name in baseline:
            dest = out / 'measured' / side / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pair / (side + '-src') / name, dest)
        shutil.copyfile(pair / side / 'attempt/supervisor.json', out / 'native' / (side + '.json'))
        shutil.copyfile(pair / side / 'isolation.json', out / 'native' / (side + '-isolation.json'))
    (out / 'native/stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    summary = dict(scan='DS26-0002', exact_science_and_eight_pngs=True, tests=tests,
                   native_seconds=comparison['observed_process_seconds'],
                   numerical_seconds={s: stages[s]['numerical'] for s in stages},
                   complete_fit_trials=means, trial_count=6, runtime_integrated=True,
                   production_modified=False, full_ds26_qualified=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    colors = ['#8796a5', '#32846b']
    names = ['Serial replay', 'Paired replay']
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    values = [[summary['native_seconds'][s] for s in ('baseline', 'optimized')],
              [stages[s]['numerical'] for s in ('baseline', 'candidate')],
              [means[s]['seconds'] for s in ('baseline', 'candidate')]]
    titles = ['Complete native run\nOne candidate-first pair; shared host',
              'Numerical replay stage\nWithin the complete native pair',
              'Complete replay fits\nMean of three alternating pairs']
    for ax, vals, title in zip(axes, values, titles, strict=True):
        bars = ax.bar(names, vals, color=colors)
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=title, ylabel='Wall seconds', ylim=(0, max(vals) * 1.22))
        ax.tick_params(axis='x', labelrotation=15)
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    for ax, metric, title in zip(axes, ('wall', 'cpu'), ('Wall time', 'Parent + child CPU'),
                                 strict=True):
        for offset, side, color in zip((-.18, .18), ('baseline', 'candidate'), colors, strict=True):
            vals = [r['seconds'] if metric == 'wall' else
                    r['self_cpu_seconds'] + r['children_cpu_seconds']
                    for r in trials if r['name'] == side]
            ax.bar(np.arange(3) + offset, vals, width=.36, label=side, color=color)
        ax.set(xticks=np.arange(3), xticklabels=['AB', 'BA', 'AB'], ylabel='Seconds', title=title)
        ax.legend()
    fig.suptitle('DS26-0002 · full fit results and ordered numerical receipts exact')
    fig.savefig(out / 'trials.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
