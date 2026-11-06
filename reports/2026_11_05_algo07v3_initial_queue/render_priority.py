"""Validate fixed-priority trials before changing the bound runtime sources."""

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    out = Path(__file__).resolve().parent
    summary = {}
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout='constrained')
    table = ['| Scan / pair | FIFO stage | Priority stage | FIFO fits | Priority fits | '
             'FIFO CPU | Priority CPU |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row, scan in enumerate(('0002', '0066')):
        root = Path(f'/srv/bulk/leo-dev/algo07v3-initialpriority-{scan}-20261106')
        result = json.loads((root / 'result.json').read_bytes())
        assert result['exact'] and len(result['rows']) == 4
        assert all(r['exact'] and r['unchanged_inputs'] for r in result['rows'])
        for path, digest in result['bindings'].items():
            assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == digest, path
        dest = out / f'priority-{scan}'
        dest.mkdir(exist_ok=True)
        for path in root.iterdir():
            if path.suffix in ('.json', '.py'):
                shutil.copyfile(path, dest / path.name)
        summary[scan] = result['means']
        for side, label, color in (('baseline', 'FIFO', '#427ba0'),
                                    ('candidate', 'Fitted-c first', '#b36dba')):
            rows = [r for r in result['rows'] if r['side'] == side]
            for ax, key, title in zip(axes[row], ('seconds', 'cpu_seconds'),
                    ('Complete initial search', 'Total CPU'), strict=True):
                ax.plot([r['pair']+1 for r in rows], [r[key] for r in rows],
                        'o-', label=label, color=color)
                ax.set(title=f'DS26-{scan}: {title}', xlabel='Alternating pair', ylabel='Seconds')
                ax.set_xticks([1, 2])
                ax.legend()
        for pair in range(2):
            a, b = [next(r for r in result['rows'] if r['pair'] == pair and r['side'] == side)
                    for side in ('baseline', 'candidate')]
            table.append(f'| DS26-{scan} / {pair+1} | {a["seconds"]:.3f} | {b["seconds"]:.3f} | '
                f'{a["branch_fit_seconds"]:.3f} | {b["branch_fit_seconds"]:.3f} | '
                f'{a["cpu_seconds"]:.3f} | {b["cpu_seconds"]:.3f} |')
    (out / 'priority-table.md').write_text('\n'.join(table)+'\n')
    (out / 'priority-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig.suptitle('Same fits and three-worker allowance; different task order')
    fig.savefig(out / 'priority.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
