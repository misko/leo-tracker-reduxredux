"""Report complete native results and the owning-worker fits actually changed."""

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    args = parser.parse_args()
    root, out = args.root, Path(__file__).resolve().parent
    plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts']
    assert comparison['external_function_substitution']
    assert not comparison['source_changes'] and not comparison['added_modules']
    parity = read(root / 'baseline-parity.json')
    assert parity['profile_science_and_eight_pngs_exact']
    checker = Path('tools/compare_algo07v3_runs.py').resolve()
    original_checker = out / 'measured/compare_algo07v3_runs.py'
    correction = comparison['validator_only_correction']
    assert correction['exact_source_patch_verified']
    assert hashlib.sha256(checker.read_bytes()).hexdigest() == correction['corrected_sha256']
    for bindings in (plan['bindings'], parity['bindings']):
        for name, sha in bindings.items():
            source = original_checker if name == str(checker) else Path(name)
            assert hashlib.sha256(source.read_bytes()).hexdigest() == sha, name
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 11
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('errors', 'failures', 'skipped'))
    fits = {s: read(root / s / 'fits.json') for s in ('baseline', 'candidate')}
    assert all(r['complete'] for rows in fits.values() for r in rows)
    keys = ('stage', 'fitted_c', 'observations', 'evaluations')
    assert [[tuple(r[k] for k in keys) for r in rows] for rows in fits.values()][0] == [
        tuple(r[k] for k in keys) for r in fits['candidate']]
    groups = defaultdict(lambda: dict(baseline=0., candidate=0.))
    for side, rows in fits.items():
        for row in rows:
            groups[row['stage']][side] += row['seconds']
    totals = {side: dict(seconds=sum(r['seconds'] for r in rows),
                        cpu_seconds=sum(r['self_cpu_seconds'] + r['children_cpu_seconds']
                                        for r in rows), fits=len(rows),
                        parallel_fits=sum(r['parallel'] for r in rows))
              for side, rows in fits.items()}
    stages = {}
    for side in fits:
        outcome = read(root / side / 'supervisor.json')
        assert outcome['returncode'] == 0 and outcome['worker']['status'] == 'complete'
        assert not outcome['worker']['resumed']
        stages[side] = {r['stage']: r['seconds'] for line in
                        (root / side / 'worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
        dest = out / side
        dest.mkdir(exist_ok=True)
        for name in ('supervisor.json', 'worker.json', 'fits.json', 'resources-start.json',
                     'resources-end.json', 'process-time.txt', 'isolation.json'):
            shutil.copyfile(root / side / name, dest / name)
    for name in ('plan.json', 'comparison.json', 'baseline-parity.json'):
        shutil.copyfile(root / name, out / name)
    shutil.copyfile(args.tests, out / 'tests.xml')
    summary = dict(scan='DS26-0002', complete_science_and_pngs_exact=True,
                   unchanged_baseline_verified=True,
                   native_seconds=comparison['observed_process_seconds'],
                   root_fit_totals=totals, root_fit_stages=dict(groups), tests=11,
                   runtime_integrated=False, production_modified=False,
                   original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (out / 'stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), layout='constrained')
    colors = ['#8796a5', '#32846b']
    values = [[comparison['observed_process_seconds'][s] for s in ('baseline', 'optimized')],
              [totals[s]['seconds'] for s in ('baseline', 'candidate')]]
    titles = ['Complete native run · one fresh pair\nIncludes unchanged stages and host variation',
              'Fits routed in owning worker\nOther worker fits remain serial internally']
    for ax, vals, title in zip(axes, values, titles, strict=True):
        bars = ax.bar(['Serial gradients', 'Parallel axes'], vals, color=colors)
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=title, ylabel='Wall seconds', ylim=(0, max(vals) * 1.2))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 4), layout='constrained')
    names = list(groups)
    for offset, side, color in zip((-.18, .18), ('baseline', 'candidate'), colors, strict=True):
        ax.bar(np.arange(len(names)) + offset, [groups[n][side] for n in names],
               width=.36, label=side, color=color)
    ax.set(xticks=np.arange(len(names)), xticklabels=names, ylabel='Root-fit wall seconds',
           title='Where gradient scheduling helps or hurts · identical scientific results')
    ax.legend()
    fig.savefig(out / 'fit-stages.png', dpi=160)
    plt.close(fig)
    names = sorted(stages['baseline'], key=stages['baseline'].get, reverse=True)[:13]
    fig, ax = plt.subplots(figsize=(10, 7), layout='constrained')
    for offset, side, color in zip((-.18, .18), ('baseline', 'candidate'), colors, strict=True):
        ax.barh(np.arange(len(names)) + offset, [stages[side][n] for n in names],
                height=.36, label=side, color=color)
    ax.set(yticks=np.arange(len(names)), yticklabels=[n.replace('_', ' ') for n in names],
           xlabel='Stage wall seconds (nested within total native time)',
           title='DS26-0002 · latest complete pair\nUnchanged stages also vary; differences are not causal speedups')
    ax.invert_yaxis()
    ax.legend()
    fig.savefig(out / 'stages.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
