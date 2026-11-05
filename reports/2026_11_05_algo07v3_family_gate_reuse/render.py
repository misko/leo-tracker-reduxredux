"""Verify receipts and render the fresh pair plus alternating full audits."""

import argparse
import hashlib
import json
import statistics
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def verify(bindings):
    for name, sha in bindings.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name


def main(root, component):
    out = Path(__file__).resolve().parent
    plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
    assert comparison['exact_owned_science_and_artifacts']
    verify(plan['bindings'])
    verify(comparison['input_bindings'])
    for name in ('plan.json', 'comparison.json', 'baseline-sources.json'):
        (out / name).write_bytes((root / name).read_bytes())
    samples = []
    for side in plan['sequence']:
        clock = read(root / side / 'attempt/supervisor.json')
        assert clock['status'] == 'exited' and clock['returncode'] == 0
        assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
        assert all(read(root / side / 'isolation.json')['checks'].values())
        rows = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                .read_text().splitlines()]
        stages = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        text = (root / f'{side}-process-time.txt').read_text()
        values = dict(line.strip().rsplit(': ', 1) for line in text.splitlines() if ': ' in line)
        assert values['Exit status'] == '0'
        samples.append(dict(side=side, seconds=clock['process_seconds'], stages=stages,
                            user_seconds=float(values['User time (seconds)']),
                            system_seconds=float(values['System time (seconds)']),
                            maximum_rss_kbytes=int(values['Maximum resident set size (kbytes)'])))
        for name in (f'{side}-process-time.txt', f'{side}-resources-start.json',
                     f'{side}-resources-end.json'):
            (out / name).write_bytes((root / name).read_bytes())
        for name, path in {'supervisor.json': 'attempt/supervisor.json',
                           'isolation.json': 'isolation.json'}.items():
            (out / f'{side}-{name}').write_bytes((root / side / path).read_bytes())
    benchmark, parity = read(component / 'benchmark.json'), read(component / 'parity.json')
    assert benchmark['worker']['status'] == 'complete' and not benchmark['changed_sources']
    assert parity['profile_science_and_eight_pngs_exact'] and parity['shared_implementation_exact']
    verify(read(component / 'plan.json')['bindings'])
    audits = read(component / 'audits.json')
    assert audits and all(a['exact'] and len(a['rows']) == 6 for a in audits)
    means = {side: {field: sum(statistics.mean(r[field] for r in a['rows']
                                              if r['side'] == side) for a in audits)
                    for field in ('seconds', 'self_cpu_seconds', 'children_cpu_seconds')}
             for side in ('baseline', 'candidate')}
    for name in ('benchmark.json', 'parity.json', 'audits.json', 'plan.json'):
        (out / ('component-' + name)).write_bytes((component / name).read_bytes())
    summary = dict(exact=True, samples=samples, component_means=means,
                   component_audits=len(audits), component_executions=6 * len(audits),
                   component_reduction_percent=100 * (1 - means['candidate']['seconds'] /
                                                     means['baseline']['seconds']),
                   production_modified=False, dataset_wide_qualification=False,
                   matched_full_scans=1, completed_full_runs=2, qualified_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout='constrained')
    colors = ['#777777', '#3465a4']
    bars = axes[0].bar([s['side'] for s in samples], [s['seconds'] for s in samples], color=colors)
    axes[0].bar_label(bars, fmt='%.2f s', padding=3)
    axes[0].set(ylabel='Elapsed seconds', title='DS26-0002 · fresh native pipeline',
                ylim=(0, max(s['seconds'] for s in samples) * 1.15))
    x = np.arange(len(audits))
    for i, side in enumerate(means):
        vals = [statistics.mean(r['seconds'] for r in a['rows'] if r['side'] == side)
                for a in audits]
        bars = axes[1].bar(x + (i - .5) * .36, vals, width=.36, color=colors[i], label=side)
        axes[1].bar_label(bars, fmt='%.3f', padding=3)
    axes[1].set(xticks=x, xticklabels=[f'Audit {i}' for i in x], ylabel='Mean elapsed seconds',
                title='Three alternating pairs per complete audit')
    axes[1].legend()
    fig.suptitle('Exact science, both calibration arms and eight PNGs\n'
                 'Capture, GLRT extraction and queue excluded; shared-host subset')
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--component', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.component)
