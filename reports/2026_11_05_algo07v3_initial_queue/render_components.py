"""Verify complete-search receipts and show latency, CPU and task scheduling."""

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    return json.loads(path.read_bytes())


def main():
    out = Path(__file__).resolve().parent
    results = {}
    for scan, count in (('0002', 6), ('0066', 4)):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-initialqueue-{scan}-20261106')
        result = read(root / 'result.json')
        assert result['exact'] and len(result['rows']) == count
        assert all(r['exact'] and r['unchanged_inputs'] for r in result['rows'])
        for path, digest in result['bindings'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
        dest = out / f'component-{scan}'
        dest.mkdir(exist_ok=True)
        for path in root.iterdir():
            if path.suffix in ('.json', '.py'):
                shutil.copyfile(path, dest / path.name)
        results[scan] = result
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), layout='constrained')
    table = ['| Scan / pair | Baseline stage | Queued stage | Baseline fits | Queued fits | '
             'Baseline CPU | Queued CPU |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row, (scan, result) in enumerate(results.items()):
        for side, color in (('baseline', '#427ba0'), ('candidate', '#41956a')):
            samples = [r for r in result['rows'] if r['side'] == side]
            for ax, key, label in zip(axes[row],
                    ('seconds', 'branch_fit_seconds', 'cpu_seconds'),
                    ('Complete initial search', 'Selected branch/arm fits', 'Parent + child CPU'),
                    strict=True):
                ax.plot([r['pair'] + 1 for r in samples], [r[key] for r in samples],
                        'o-', color=color, label=side)
                ax.set(title=f'DS26-{scan}: {label}', xlabel='Alternating pair', ylabel='Seconds')
                ax.set_xticks(range(1, len(samples)+1))
                ax.legend()
        for pair in range(len(result['rows'])//2):
            a, b = [next(r for r in result['rows'] if r['pair'] == pair and r['side'] == side)
                    for side in ('baseline', 'candidate')]
            table.append(f'| DS26-{scan} / {pair+1} | {a["seconds"]:.3f} | {b["seconds"]:.3f} | '
                f'{a["branch_fit_seconds"]:.3f} | {b["branch_fit_seconds"]:.3f} | '
                f'{a["cpu_seconds"]:.3f} | {b["cpu_seconds"]:.3f} |')
    (out / 'component-table.md').write_text('\n'.join(table)+'\n')
    fig.suptitle('Same full initial searches and callbacks; at most three fitting workers')
    fig.savefig(out / 'components.png', dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(12, 6), layout='constrained')
    for ax, side in zip(axes, ('baseline', 'candidate'), strict=True):
        row = next(r for r in results['0066']['rows'] if r['pair'] == 0 and r['side'] == side)
        tasks = [t for block in row['blocks'] for t in block['tasks']]
        origin = min(t['start'] for t in tasks)
        for i, task in enumerate(tasks):
            branch, arm = task['task']
            ax.barh(i, task['end']-task['start'], left=task['start']-origin,
                    color='#427ba0' if arm == 'c0' else '#41956a')
        ax.set_yticks(range(len(tasks)), [f'Branch {t["task"][0]} / {t["task"][1]}' for t in tasks])
        ax.invert_yaxis()
        ax.set(title=side, xlabel='Seconds from first fit start')
    fig.suptitle('DS26-0066 / first pair: observed task execution intervals\n'
                 'Same six fits; baseline waits for each branch pair')
    fig.savefig(out / 'schedule.png', dpi=160)
    plt.close(fig)
    summary = {scan: r['means'] for scan, r in results.items()}
    (out / 'component-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
