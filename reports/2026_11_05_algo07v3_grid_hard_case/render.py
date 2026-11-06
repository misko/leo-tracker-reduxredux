"""Publish hard-scan native parity and the separate gradient-axis experiment."""

import argparse
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def verify(bindings):
    for name, sha in bindings.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', type=Path, required=True)
    parser.add_argument('--gradient', type=Path, required=True)
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    comparison = read(args.pair / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts'] and comparison['both_c_arms']
    verify(read(args.pair / 'plan.json')['bindings'])
    verify(read(args.gradient / 'plan.json')['bindings'])
    history = read(args.pair / 'history-parity.json')
    assert history['exact'] and not history['failures']
    verify(history['bindings'])
    tests = list(ET.parse(args.pair / 'gradient-tests.xml').getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in tests) == 4
    assert all(int(s.attrib[k]) == 0 for s in tests for k in ('errors', 'failures', 'skipped'))
    rows = [read(p) for p in sorted(args.gradient.glob('*-*-*.json'))
            if p.name.startswith(('c0-', 'fitted_c-'))]
    assert len(rows) == 4 and all(r['exact'] for r in rows)
    grad = {arm: {side: next(r for r in rows if r['arm'] == arm and r['side'] == side)
                  for side in ('baseline', 'candidate')} for arm in ('c0', 'fitted_c')}
    stages = {}
    summaries = {}
    for side in ('baseline', 'candidate'):
        outcome = read(args.pair / side / 'attempt/supervisor.json')
        assert outcome['status'] == 'exited' and outcome['returncode'] == 0
        assert outcome['worker']['status'] == 'complete' and not outcome['worker']['resumed']
        summaries[side] = outcome['worker']['publication']['arms']
        stages[side] = {r['stage']: r['seconds'] for line in
                        (args.pair / side / 'attempt/worker.log').read_text().splitlines()
                        if (r := json.loads(line)).get('event') == 'stage'}
    assert summaries['baseline'] == summaries['candidate']
    for directory, names, dest_name in (
        (args.pair, ['comparison.json', 'plan.json', 'baseline-sources.json',
                     'candidate-sources.json', 'baseline-process-time.txt',
                     'candidate-process-time.txt', 'baseline-resources-start.json',
                     'baseline-resources-end.json', 'candidate-resources-start.json',
                     'candidate-resources-end.json', 'gradient-tests.xml',
                     'history-parity.json', 'baseline-midrun-resources.json'], 'native'),
        (args.gradient, ['plan.json', 'result.json', 'original.py', 'candidate.py',
                         *[p.name for p in sorted(args.gradient.glob('*-*-*.json'))
                           if p.name.startswith(('c0-', 'fitted_c-'))]], 'gradient')):
        dest = out / dest_name
        dest.mkdir(exist_ok=True)
        for name in names:
            shutil.copyfile(directory / name, dest / name)
    for side in stages:
        for src, name in (('attempt/supervisor.json', 'outcome'), ('isolation.json', 'isolation')):
            shutil.copyfile(args.pair / side / src, out / 'native' / f'{side}-{name}.json')
    summary = dict(
        scan='DS26-0066', exact_native=True, historical_science_and_pngs_exact=True,
        native_seconds=comparison['observed_process_seconds'],
        grid_stage_seconds={s: stages[s]['plot_evidence'] for s in stages},
        arms=summaries['candidate'],
        gradient={arm: {side: {k: row[k] for k in ('seconds', 'self_cpu_seconds',
                                                  'children_cpu_seconds', 'exact')}
                        for side, row in sides.items()} for arm, sides in grad.items()},
        gradient_runtime_integrated=False, production_modified=False,
        full_ds26_qualification=False, original_algo07_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    (out / 'native/stages.json').write_text(json.dumps(stages, indent=2) + '\n')
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout='constrained')
    colors = ['#8796a5', '#32846b']
    values = [[comparison['observed_process_seconds'][s] for s in ('baseline', 'optimized')],
              [stages[s]['plot_evidence'] for s in ('baseline', 'candidate')],
              [grad['c0'][s]['seconds'] for s in ('baseline', 'candidate')]]
    titles = ['DS26-0066 complete native run\nOne candidate-first pair',
              'Final grid + plot evidence\nThree batches: unchanged science',
              'Separate c=0 training fit\nExperimental parallel gradient axes']
    for ax, vals, title in zip(axes, values, titles, strict=True):
        bars = ax.bar(['Reference', 'Candidate'], vals, color=colors)
        ax.bar_label(bars, fmt='%.2f s', padding=4)
        ax.set(title=title, ylabel='Wall seconds', ylim=(0, max(vals) * 1.22))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
