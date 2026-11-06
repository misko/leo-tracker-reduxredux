"""Render complete annotation-queue comparisons and measured task intervals."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


def jobs(row):
    labels = next((b['entries'] for b in row['blocks'] if b['kind'] == 'global_task_labels'), None)
    output = []
    for block in row['blocks']:
        if block['kind'] != 'training':
            continue
        for item in block['tasks']:
            target = block.get('target')
            if target is None:
                pair, arm = item['item']
                target = labels[2 * pair + int(arm == 'fitted_c')][0]
            output.append(dict(item, target=target))
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair', type=Path, action='append', required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    results, summary = [], []
    for index, directory in enumerate(args.pair):
        result = json.loads((directory / 'result.json').read_bytes())
        assert result['exact']
        for original, sha in result['plan']['bindings'].items():
            path = Path(original)
            archived = root / 'baseline-src' / str(path).split('/src/')[-1]
            if not any(q.is_file() and hashlib.sha256(q.read_bytes()).hexdigest() == sha
                       for q in (path, archived)):
                raise ValueError(f'Bound input/source changed: {path}')
        signatures = [r['signature'] for r in result['rows']]
        assert all(s == signatures[0] for s in signatures)
        # Full identical signatures repeat megabytes of optimizer metadata.
        # Keep their digest, every timing/binding and the raw receipt digest.
        compact = dict(result, raw_result=dict(path=str(directory / 'result.json'),
                       sha256=hashlib.sha256((directory / 'result.json').read_bytes()).hexdigest()))
        compact['rows'] = [dict(
            {k: v for k, v in row.items() if k != 'signature'},
            signature_sha256=hashlib.sha256(json.dumps(row['signature'], sort_keys=True).encode())
            .hexdigest()) for row in result['rows']]
        (root / f'pair-{index}.json').write_text(json.dumps(compact, indent=2) + '\n')
        results.append(result)
        a, b = [next(r for r in result['rows'] if r['side'] == side)
                for side in ('baseline', 'candidate')]
        assert all(r['exact'] and r['saved_votes_exact'] and r['unchanged_inputs']
                   for r in result['rows'])
        summary.append(dict(label=directory.name, baseline_seconds=a['seconds'],
                            candidate_seconds=b['seconds'],
                            reduction_percent=100 * (1 - b['seconds'] / a['seconds']),
                            baseline_cpu_seconds=a['cpu_seconds'],
                            candidate_cpu_seconds=b['cpu_seconds'],
                            training_jobs=len(jobs(a)), candidate_first=result['plan']['reverse']))
    (root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True, layout='constrained')
    colors = plt.get_cmap('tab10')
    for ax, side in zip(axes, ('baseline', 'candidate'), strict=True):
        row = next(r for r in results[0]['rows'] if r['side'] == side)
        work = sorted(jobs(row), key=lambda r: r['start'])
        origin = min(b['start'] for b in row['blocks'] if b['kind'] == 'training')
        ends = [0., 0., 0.]
        for job in work:
            start, end = job['start'] - origin, job['end'] - origin
            lane = min(range(3), key=ends.__getitem__)
            assert ends[lane] <= start
            ends[lane] = end
            ax.broken_barh([(start, end-start)], (lane-.35, .7),
                           facecolors=colors(job['target']), edgecolors='white', linewidth=.4)
        ax.set_yticks([0, 1, 2], ['Slot 1', 'Slot 2', 'Slot 3'])
        ax.set_title(f"{side.title()}: all annotations {row['seconds']:.1f} s; "
                     f"CPU {row['cpu_seconds']:.1f} s")
        ax.grid(alpha=.2, axis='x')
    axes[-1].set_xlabel('Seconds from first training queue; slots reconstructed from intervals')
    axes[0].legend(handles=[Patch(facecolor=colors(i), label=f'Target {i}') for i in range(8)],
                   ncol=8, loc='upper center', bbox_to_anchor=(.5, 1.32))
    fig.suptitle('DS26-0066: unchanged training jobs, three workers\n'
                 'Blank intervals also include scoring and orchestration', y=1.07)
    fig.savefig(root / 'timeline.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    table = '\n'.join(f"| {r['label']} | {r['baseline_seconds']:.3f} | "
                      f"{r['candidate_seconds']:.3f} | {r['reduction_percent']:+.2f}% | "
                      f"{r['baseline_cpu_seconds']:.3f} | {r['candidate_cpu_seconds']:.3f} |"
                      for r in summary)
    (root / 'measurements.md').write_text(f'''# Complete annotation comparisons

| Pair | Baseline s | Candidate s | Time reduction | Baseline CPU s | Candidate CPU s |
| --- | ---: | ---: | ---: | ---: | ---: |
{table}

Every full annotation and saved vote is exact, and tracked input fingerprints
are unchanged. Both calibration arms, all original targets/folds/priors and
iteration budgets are retained. Three CPUs and one BLAS thread per worker.
These clocks include training, recipe reconstruction and annotation scoring;
they exclude loading the prepared context and later inclusion/publication.
Instrumentation is matched on both sides. These are not complete-scan speedups.

![Measured training intervals](timeline.png)
''')


if __name__ == '__main__':
    main()
