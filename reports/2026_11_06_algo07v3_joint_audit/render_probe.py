"""Render verified same-checkpoint audit timings without claiming pipeline gain."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verified = json.loads((args.root / 'verified.json').read_bytes())
    assert verified['bindings_unchanged'] and verified['exact_complete_grid']
    plan = json.loads((args.root / 'plan.json').read_bytes())
    for path, sha in plan['bindings'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
    rows = json.loads((args.root / 'result.json').read_bytes())['rows']
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate', 'baseline']
    assert all(r['exact'] and np.array(r['scores']).shape == (5, 3) for r in rows)
    assert len({(r['score_signature'], r['policy_signature']) for r in rows}) == 1
    summary = {side: {field: float(np.mean([r[field] for r in rows if r['side'] == side]))
                      for field in ('seconds', 'cpu_seconds')}
               for side in ('baseline', 'candidate')}
    summary['scope'] = plan['scope'] + '; identical native checkpoint'
    summary['full_pipeline_speedup'] = None
    args.output.mkdir(exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    lines = ['| Trial | Execution | Wall seconds | CPU seconds |', '| ---: | --- | ---: | ---: |']
    for row in rows:
        lines.append(f"| {row['index']} | {row['side']} | {row['seconds']:.3f} | "
                     f"{row['cpu_seconds']:.3f} |")
    (args.output / 'timings.md').write_text('\n'.join(lines) + '\n')
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    for axis, field, title in zip(axes, ('seconds', 'cpu_seconds'),
                                  ('Elapsed time', 'CPU including audit children'), strict=True):
        for a, b in ((rows[0], rows[1]), (rows[3], rows[2])):
            axis.plot([0, 1], [a[field], b[field]], 'o-', alpha=.75)
        axis.set(xticks=[0, 1], xticklabels=['Serial audit', 'Three process batches'],
                 ylabel='Seconds', title=title,
                 ylim=(0, max(row[field] for row in rows) * 1.12))
        axis.grid(axis='y', alpha=.25)
    route = 'predictive recovery' if 'predictive' in plan['scope'] else 'numerical replay'
    figure.suptitle(f'DS26-0102 · {route}, c=0 · all 15 scores exact')
    figure.text(.5, .01, 'Two alternating pairs; quadrature only. '
                'Native prefix and publication excluded.',
                ha='center', fontsize=9)
    figure.tight_layout(rect=(0, .04, 1, .93))
    figure.savefig(args.output / 'audit-grid.png', dpi=160)
    plt.close(figure)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
