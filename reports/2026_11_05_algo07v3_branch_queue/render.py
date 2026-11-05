"""Verify and render alternating complete initial-search experiments."""
import argparse
import hashlib
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('tests', type=Path)
    args = parser.parse_args()
    dest = Path(__file__).resolve().parent
    result = json.loads((args.source / 'result.json').read_text())
    rows = result['rows']
    assert result['exact'] and len(rows) == 6 and all(r['exact'] for r in rows)
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate',
                                       'baseline', 'baseline', 'candidate']
    for path, sha in result['bindings'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 5
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    for old, new in [('result.json', 'result.json'), ('plan.json', 'plan.json'),
                     ('original.txt', 'original-search.txt'),
                     ('candidate.txt', 'queued-search.txt')]:
        (dest / new).write_bytes((args.source / old).read_bytes())
    (dest / 'tests.xml').write_bytes(args.tests.read_bytes())
    means = {side: dict(seconds=statistics.mean(r['seconds'] for r in rows if r['side'] == side),
                        cpu_seconds=statistics.mean(sum(r['cpu_seconds'])
                                                    for r in rows if r['side'] == side))
             for side in ('baseline', 'candidate')}
    summary = dict(means=means, exact=True, full_pipeline_speedup=None,
                   elapsed_reduction_percent=100 * (
                       1 - means['candidate']['seconds'] / means['baseline']['seconds']),
                   cpu_change_percent=100 * (
                       means['candidate']['cpu_seconds'] / means['baseline']['cpu_seconds'] - 1),
                   maximum_workers=result['max_workers'],
                   fully_fitted_hypotheses=[r['fully_fitted_hypotheses'] for r in rows])
    (dest / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, key, title in zip(axes, ('seconds', 'cpu_seconds'),
                              ('Complete initial-search elapsed seconds',
                               'Parent + reaped-child CPU seconds'), strict=True):
        maximum = 0
        for side, offset, color in [('baseline', -.18, '#68778b'), ('candidate', .18, '#168579')]:
            subset = [r for r in rows if r['side'] == side]
            values = [sum(r[key]) if isinstance(r[key], list) else r[key] for r in subset]
            maximum = max(maximum, max(values))
            bars = ax.bar([r['pair'] + offset for r in subset], values, width=.35,
                          label=side, color=color)
            ax.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3, fontsize=9)
        ax.set_xticks([0, 1, 2], ['B → C', 'C → B', 'B → C'])
        ax.set_ylim(0, maximum * 1.18)
        ax.set_ylabel(title)
        ax.grid(axis='y', alpha=.2)
    axes[1].legend(loc='upper center', bbox_to_anchor=(.5, 1.15), ncol=2)
    fig.suptitle('DS26-0002 · sequential branch pairs versus shared three-worker queue\n'
                 'All six full initial searches exact; prepared-stage benchmark')
    fig.savefig(dest / 'initial-search.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
