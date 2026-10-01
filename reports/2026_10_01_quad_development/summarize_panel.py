"""Write an immutable snapshot, including every pending or failed planned unit."""
import argparse
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from build_selection import digest

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    if Path(args.name).name != args.name:
        raise ValueError('snapshot name must be a basename')
    output = HERE / (args.name + '.json')
    if any(output.with_suffix(ext).exists() for ext in ['.json', '.sha256', '.png']):
        raise FileExistsError(output)
    selection_path = HERE / 'selection.json'
    assert digest(selection_path) == selection_path.with_suffix('.sha256').read_text().strip()
    selection = json.loads(selection_path.read_text())
    planned = {u['unit_id']: u for u in selection['evaluation_units']}
    blocks = list(dict.fromkeys(u['block_id'] for u in planned.values()))
    observed = {}
    sources = {str(selection_path): digest(selection_path)}
    for block in blocks:
        path = HERE / 'independent-v2' / block / 'evaluation.json'
        if not path.exists():
            continue
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        data = json.loads(path.read_text())['rows']
        expected = {u for u, row in planned.items() if row['block_id'] == block}
        assert len(data) == 7 and {r['unit'] for r in data} == expected
        sources[str(path)] = digest(path)
        for row in data:
            assert row['size'] == planned[row['unit']]['size']
            assert row['scans'] == planned[row['unit']]['scans']
            observed[row['unit']] = row
    rows = [observed.get(unit, dict(unit=unit, block_id=u['block_id'],
            size=u['size'], scans=u['scans'], accepted=False, pending=True))
            for unit, u in planned.items()]
    summary = {}
    for size in [1, 2, 4]:
        selected = [r for r in rows if r['size'] == size]
        completed = [r for r in selected if not r.get('pending', False)]
        errors = [r['error_m'] for r in completed if r['accepted']]
        summary[str(size)] = dict(planned=len(selected), audited=len(completed),
            pending=len(selected)-len(completed), accepted=len(errors),
            rejected=len(completed)-len(errors),
            median_error_m=float(np.median(errors)) if errors else None,
            p90_error_m=float(np.percentile(errors, 90)) if errors else None,
            within1000m=sum(e <= 1000 for e in errors),
            within3000m=sum(e <= 3000 for e in errors),
            median_runtime_s=float(np.median([r['runtime_s'] for r in completed])) if completed else None)
    document = dict(summary=summary, rows=rows, source_sha256=sources,
        summarizer_sha256=digest(__file__),
        qualification='Development snapshot, not heldout validation. Error quantiles condition on accepted outcomes. Pending units are explicit, not scored as failures. Nested windows and nearby blocks are correlated; do not treat the112 units as independent.')
    with output.open('x') as stream:
        json.dump(document, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    colors = plt.get_cmap('tab20')
    for index, block in enumerate(blocks):
        prefix = [observed.get(block + suffix) for suffix in ['-S1', '-D1', '-Q']]
        if not any(prefix):
            continue
        values = [r['error_m'] if r and r['accepted'] else np.nan for r in prefix]
        axes[0].plot([1, 2, 4], values, '-o', color=colors(index), label=block)
    axes[0].set_xticks([1, 2, 4], ['A: single', 'AB: pair', 'ABCD: quad'])
    axes[0].set_ylabel('Horizontal error (m)')
    axes[0].legend(fontsize=8)
    axes[0].set_title('Matched prefixes; each line is one block')
    for size, label in [(1, 'Singles'), (2, 'Pairs'), (4, 'Quads')]:
        errors = sorted(r['error_m'] for r in observed.values() if r['size'] == size and r['accepted'])
        if errors:
            axes[1].step(errors, np.arange(1, len(errors)+1)/len(errors), where='post', label=f'{label} (n={len(errors)})')
    axes[1].set_xscale('log')
    axes[1].set_xlabel('Horizontal error (m, logarithmic scale)')
    axes[1].set_ylabel('Fraction of accepted fits')
    axes[1].set_title('Empirical distributions of completed accepted fits')
    axes[1].legend()
    for ax in axes:
        ax.grid(alpha=.2)
    fig.suptitle(f'Expanded development panel: {len(observed)}/112 windows audited\nIndependent scan clocks; pending windows excluded from error distributions')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
