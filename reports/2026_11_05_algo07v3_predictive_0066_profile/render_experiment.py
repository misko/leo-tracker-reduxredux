"""Publish the exact paired-arm fold experiment separately from pipeline timing."""
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
    data = json.loads((args.source / 'result.json').read_text())
    rows = data['rows']
    assert len(rows) == 6 and all(r['exact'] for r in rows) and data['exact']
    assert all(r['fingerprint'] == rows[0]['fingerprint'] for r in rows)
    for path, sha in data['bindings'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
    tests = ET.fromstring(args.tests.read_text())
    assert sum(int(t.attrib['tests']) for t in tests) == 5
    assert not any(int(t.attrib[k]) for t in tests for k in ('errors', 'failures', 'skipped'))
    for source, target in [('result.json', 'experiment.json'),
                           ('original.txt', 'original-fold.txt'),
                           ('candidate.txt', 'candidate-fold.txt')]:
        (dest / target).write_bytes((args.source / source).read_bytes())
    (dest / 'experiment-tests.xml').write_bytes(args.tests.read_bytes())
    summary = {}
    for side in ('baseline', 'candidate'):
        subset = [r for r in rows if r['side'] == side]
        summary[side] = dict(
            mean_seconds=statistics.mean(r['seconds'] for r in subset),
            mean_cpu_seconds=statistics.mean(sum(r['cpu_seconds']) for r in subset))
    summary['elapsed_reduction_percent'] = 100 * (
        1 - summary['candidate']['mean_seconds'] / summary['baseline']['mean_seconds'])
    summary['cpu_change_percent'] = 100 * (
        summary['candidate']['mean_cpu_seconds'] / summary['baseline']['mean_cpu_seconds'] - 1)
    summary.update(exact=True, complete_fold_comparisons=6, full_pipeline_qualified=False)
    (dest / 'experiment-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    for ax, key, title in zip(axes, ('seconds', 'cpu_seconds'),
                              ('Elapsed seconds', 'Parent + child CPU seconds'), strict=True):
        for offset, side, color in [(-.18, 'baseline', '#68778b'), (.18, 'candidate', '#168579')]:
            selected = [r for r in rows if r['side'] == side]
            values = [sum(r[key]) if isinstance(r[key], list) else r[key] for r in selected]
            bars = ax.bar([r['pair'] + offset for r in selected], values,
                          width=.35, label=side, color=color)
            ax.bar_label(bars, labels=[f'{v:.2f}' for v in values], padding=3, fontsize=9)
        ax.set_xticks([0, 1, 2], ['B → C', 'C → B', 'B → C'])
        ax.set_ylabel(title)
        maximum = max(sum(r[key]) if isinstance(r[key], list) else r[key] for r in rows)
        ax.set_ylim(0, maximum * 1.18)
        ax.grid(axis='y', alpha=.2)
    axes[1].legend(loc='upper center', bbox_to_anchor=(.5, 1.15), ncol=2)
    fig.suptitle('DS26-0066 · target 1 / seed 94721 · complete prepared annotation fold\n'
                 'Exact serial versus paired training; not a full-pipeline benchmark')
    fig.savefig(dest / 'paired-training.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
