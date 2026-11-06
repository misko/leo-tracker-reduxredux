"""Archive completed prepared-search experiments and render their timings."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    output = Path(__file__).resolve().parent
    summaries = []
    for scan in ('0002', '0066'):
        source = Path(f'/srv/bulk/leo-dev/algo07v3-idle-derivatives-{scan}-20261106')
        raw = (source/'result.json').read_bytes()
        result = json.loads(raw)
        assert result['exact'] and all(row['exact'] for row in result['rows'])
        (output/f'{scan}.json').write_bytes(raw)
        for name in ('original_executor', 'generated_executor',
                     'original_gradient', 'generated_gradient'):
            data = (source/f'{name}.py').read_bytes().rstrip(b'\n') + b'\n'
            if scan == '0002':
                (output/f'{name}.py').write_bytes(data)
            else:
                assert (output/f'{name}.py').read_bytes() == data
        rows = {row['side']: row for row in result['rows']}
        baseline, candidate = rows['baseline'], rows['candidate']
        summaries.append(dict(
            scan=scan, source=str(source), sha256=hashlib.sha256(raw).hexdigest(),
            order=[r['side'] for r in result['rows']], exact=True,
            baseline_seconds=baseline['seconds'], candidate_seconds=candidate['seconds'],
            baseline_cpu_seconds=baseline['cpu_seconds'],
            candidate_cpu_seconds=candidate['cpu_seconds'],
            wall_change_pct=100*(candidate['seconds']/baseline['seconds']-1),
            cpu_change_pct=100*(candidate['cpu_seconds']/baseline['cpu_seconds']-1),
            borrowed_gradients=sum(t['borrowed_gradients'] for t in candidate['tasks'])))
    (output/'summary.json').write_text(json.dumps(dict(
        scope='Prepared complete initial search; not full pipeline',
        adopted=False, production_modified=False, rows=summaries), indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for ax, metric, ylabel in zip(axes, ('seconds', 'cpu_seconds'),
                                  ('Elapsed seconds', 'CPU seconds'), strict=True):
        for offset, side, color in ((-.18, 'baseline', '#4477aa'),
                                    (.18, 'candidate', '#cc6677')):
            bars = ax.bar([i+offset for i in range(2)],
                          [r[f'{side}_{metric}'] for r in summaries],
                          width=.36, label=side.title(), color=color)
            ax.bar_label(bars, fmt='%.1f', padding=3)
        ax.set_xticks([0, 1], ['DS26-0002', 'DS26-0066'])
        ax.set_ylabel(ylabel)
        ax.set_ylim(0, ax.get_ylim()[1]*1.13)
        ax.grid(axis='y', alpha=.2)
        ax.legend()
    fig.suptitle('Idle derivative helper: exact results, slower initial search\n'
                 'One pair per scan; three-CPU allowance; runtime unchanged')
    fig.savefig(output/'comparison.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()
