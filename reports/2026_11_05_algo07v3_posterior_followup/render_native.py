"""Verify and publish the covariance-index native comparison."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root, out=None, scan='DS26-0002'):
    out = Path(__file__).resolve().parent if out is None else out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan, comparison = read(root / 'plan.json'), read(root / 'comparison.json')
    module = 'leo/analysis/localization_v3/hierarchical.py'
    baseline = read(root / 'baseline-sources.json')
    candidate = read(root / 'candidate-sources.json')
    integrated = Path('src', module).resolve()
    for bindings in (plan['bindings'], comparison['input_bindings']):
        for name, digest in bindings.items():
            actual = hashlib.sha256(Path(name).read_bytes()).hexdigest()
            if actual != digest and Path(name) == integrated and actual == candidate[module]:
                # Promotion installs exactly the separately qualified overlay.
                assert digest == baseline[module], name
            else:
                assert actual == digest, name
    assert comparison['exact_owned_science_and_artifacts']
    assert comparison['source_changes'] == ['leo.analysis.localization_v3.hierarchical']
    counts = {}
    for name in ('tests.xml', 'prototype-tests.xml'):
        suites = list(ET.parse(root / name).getroot().iter('testsuite'))
        assert all(int(s.attrib[k]) == 0 for s in suites
                   for k in ('failures', 'errors', 'skipped'))
        counts[name] = sum(int(s.attrib['tests']) for s in suites)
    for name in ('plan.json', 'comparison.json', 'baseline-sources.json',
                 'candidate-sources.json', 'tests.xml', 'prototype-tests.xml'):
        (out / name).write_bytes((root / name).read_bytes())
    times, stages, resources = {}, {}, {}
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
    summary = dict(scan=scan, exact=True, seconds=times, stages=stages, resources=resources,
                   observed_reduction_percent=100 * (1 - times['candidate'] / times['baseline']),
                   qualified_speedup=None, production_modified=False,
                   full_dataset_equivalence=False, test_runs=counts)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    colors = ['#777777', '#3465a4']
    bars = axes[0].bar(['Original covariance gathering', 'Precomputed covariance indices'],
                       list(times.values()), color=colors)
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Native GLRT ready → supervisor exit (seconds)',
                title=f'{scan} · full pipeline observation',
                ylim=(0, max(times.values()) * 1.16))
    labels = sorted(stages['baseline'], key=stages['baseline'].get, reverse=True)[:7][::-1]
    y = np.arange(len(labels))
    for i, side in enumerate(times):
        axes[1].barh(y + (i - .5) * .36, [stages[side][k] for k in labels],
                     height=.36, color=colors[i], label=side)
    axes[1].set(yticks=y, yticklabels=labels, xlabel='Observed wall seconds',
                title='Largest stages · both arms and all science exact')
    axes[1].legend()
    fig.text(.5, .02, 'Eight PNGs and publication exact · shared-host observation, '
             'not an attributable overall speed ratio\n'
             'Capture, GLRT extraction and queue delay excluded', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .08, 1, 1))
    fig.savefig(out / 'runtime.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--scan', default='DS26-0002')
    args = parser.parse_args()
    main(args.root, args.out, args.scan)
