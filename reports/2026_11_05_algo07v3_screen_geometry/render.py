"""Publish exact residual-screen geometry reuse and complete-path timing."""

import argparse
import hashlib
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main(root):
    out = Path(__file__).resolve().parent
    plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
    for bindings in (plan['bindings'], comparison['input_bindings']):
        for name, digest in bindings.items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    assert comparison['exact_owned_science_and_artifacts']
    component = read(root / 'component-pairs.json')
    assert component['exact'] and len(component['rows']) == 6
    for name, digest in component['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    suites = list(ET.parse(root / 'tests.xml').getroot().iter('testsuite'))
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    count = sum(int(s.attrib['tests']) for s in suites)
    times, stages, resources = {}, {}, {}
    copies = ['plan.json', 'comparison.json', 'tests.xml', 'test-command.json',
              'baseline-sources.json', 'component-pairs.json', 'benchmark-tests.xml']
    for name in copies:
        (out / name).write_bytes((root / name).read_bytes())
    for side in ('baseline', 'candidate'):
        clock = read(root / side / 'attempt/supervisor.json')
        assert clock['status'] == 'exited' and clock['returncode'] == 0
        assert clock['worker']['status'] == 'complete' and not clock['worker']['resumed']
        assert all(read(root / side / 'isolation.json')['checks'].values())
        times[side] = clock['process_seconds']
        rows = [json.loads(line) for line in (root / side / 'attempt/worker.log')
                .read_text().splitlines()]
        stages[side] = {r['stage']: r['seconds'] for r in rows if r.get('event') == 'stage'}
        text = (root / f'{side}-process-time.txt').read_text()
        values = dict(line.strip().rsplit(': ', 1) for line in text.splitlines() if ': ' in line)
        assert values['Exit status'] == '0'
        resources[side] = dict(user_seconds=float(values['User time (seconds)']),
                               system_seconds=float(values['System time (seconds)']),
                               maximum_rss_kbytes=int(values['Maximum resident set size (kbytes)']))
        for name in (f'{side}-process-time.txt', f'{side}-resources-start.json',
                     f'{side}-resources-end.json'):
            (out / name).write_bytes((root / name).read_bytes())
        for name, path in {'supervisor.json': 'attempt/supervisor.json',
                           'isolation.json': 'isolation.json'}.items():
            (out / f'{side}-{name}').write_bytes((root / side / path).read_bytes())
    reduction = 100 * (1 - times['candidate'] / times['baseline'])
    summary = dict(exact=True, seconds=times, stages=stages, resources=resources,
                   observed_reduction_percent=reduction, qualified_speedup=None,
                   production_modified=False, full_dataset_equivalence=False,
                   component_tests=count)
    summary['component_means'] = {
        side: {key: statistics.mean(r[key] for r in component['rows'] if r['side'] == side)
               for key in ('seconds', 'cpu_seconds')}
        for side in ('baseline', 'candidate')}
    summary['component_reduction_percent'] = 100 * (
        1 - summary['component_means']['candidate']['seconds'] /
        summary['component_means']['baseline']['seconds'])
    write(out / 'summary.json', summary)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    colors = ['#777777', '#3465a4']
    bars = axes[0].bar(['Separate phase interpolation', 'Shared phase interpolation'],
                       list(times.values()),
                       color=colors)
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Native GLRT ready → supervisor exit (seconds)',
                title='Complete pipeline · host load changed',
                ylim=(0, max(times.values()) * 1.16))
    labels = sorted(stages['baseline'], key=stages['baseline'].get, reverse=True)[:7][::-1]
    y = np.arange(len(labels))
    for i, side in enumerate(times):
        axes[1].barh(y + (i - .5) * .36, [stages[side][k] for k in labels],
                     height=.36, color=colors[i], label=side)
    axes[1].set(yticks=y, yticklabels=labels, xlabel='Observed wall seconds',
                title='Largest stages · exact same scientific results')
    axes[1].legend()
    fig.text(.5, .02, 'Both calibration arms, all eight PNGs and publication exact · '
             'not an attributable overall speed ratio · capture/GLRT extraction/queue excluded',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    xx = np.arange(3)
    for i, side in enumerate(('baseline', 'candidate')):
        values = [r['seconds'] for r in component['rows'] if r['side'] == side]
        bars = ax.bar(xx + (i - .5) * .36, values, width=.36, color=colors[i], label=side)
        ax.bar_label(bars, fmt='%.2f', padding=3)
    ax.set(xticks=xx, xticklabels=['Baseline first', 'Candidate first', 'Baseline first'],
           ylabel='Complete residual-screen seconds',
           title='DS26-0002 · three alternating prepared-component pairs', ylim=(0, 23))
    ax.legend()
    fig.text(.5, .02, 'All screens exact · 11,144 causal candidates · three targets · '
             'one CPU / one BLAS thread · excludes upstream inference', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, 1))
    fig.savefig(out / 'component.png', dpi=160)
    plt.close(fig)

    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    main(args.root)
