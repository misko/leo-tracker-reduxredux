"""Verify and publish the independent discovery scheduling experiment."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def main(root, tests, process_time):
    out = Path(__file__).resolve().parent
    result = json.loads((root / 'result.json').read_bytes())
    assert result['exact'] and not result['runtime_modified']
    assert len(result['rows']) == 6 and all(row['exact'] for row in result['rows'])
    assert [r['side'] for r in result['rows']] == [
        'baseline', 'candidate', 'candidate', 'baseline', 'baseline', 'candidate']
    for name, sha in result['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    assert hashlib.sha256((root / 'original.py').read_bytes()).hexdigest() == (
        result['source_sha256'])
    assert hashlib.sha256((root / 'candidate.py').read_bytes().removesuffix(b'\n')).hexdigest() == (
        result['candidate_sha256'])
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 9
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ('failures', 'errors', 'skipped'))
    for name, target in {'result.json': 'discovery-result.json',
                         'original.py': 'discovery-original-source.txt',
                         'candidate.py': 'discovery-candidate-source.txt'}.items():
        (out / target).write_bytes((root / name).read_bytes())
    (out / 'discovery-tests.xml').write_bytes(tests.read_bytes())
    (out / 'discovery-process-time.txt').write_bytes(process_time.read_bytes())
    means = result['means']
    cpu = {side: row['self_cpu_seconds'] + row['children_cpu_seconds']
           for side, row in means.items()}
    summary = dict(means=means, cpu_seconds=cpu,
                   initial_reduction_percent=100 * (
                       1 - means['candidate']['seconds'] / means['baseline']['seconds']),
                   discovery_reduction_percent=100 * (
                       1 - means['candidate']['discovery_seconds'] /
                       means['baseline']['discovery_seconds']),
                   cpu_increase_percent=100 * (cpu['candidate'] / cpu['baseline'] - 1))
    (out / 'discovery-summary.json').write_text(json.dumps(summary, indent=2) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    colors = ['#777777', '#3465a4']
    for ax, field, title in zip(axes, ('seconds', 'discovery_seconds', 'cpu'),
                               ('Complete initial search', 'Discovery portion',
                                'Parent + child CPU'), strict=True):
        top = 0
        for i, side in enumerate(('baseline', 'candidate')):
            rows = [r for r in result['rows'] if r['side'] == side]
            values = [r['self_cpu_seconds'] + r['children_cpu_seconds']
                      if field == 'cpu' else r[field] for r in rows]
            top = max(top, max(values))
            bars = ax.bar(np.arange(3) + (i - .5) * .36, values,
                          width=.36, color=colors[i], label=side)
            ax.bar_label(bars, fmt='%.2f', padding=3, fontsize=8)
        ax.set(title=title, ylabel='Seconds', ylim=(0, top * 1.18), xticks=np.arange(3),
               xticklabels=['B first', 'C first', 'B first'])
    fig.suptitle('DS26-0002 · all six initial searches exactly match the owned native result')
    fig.legend(*axes[0].get_legend_handles_labels(), loc='upper center',
               bbox_to_anchor=(.5, .91), ncol=2)
    fig.text(.5, .02, 'Three CPUs / one BLAS thread · fresh context outside timer · '
             'same seeds, refinement rounds, branch budgets and both c arms',
             ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .06, 1, .86))
    fig.savefig(out / 'discovery.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--process-time', type=Path, required=True)
    args = parser.parse_args()
    main(args.root, args.tests, args.process_time)
