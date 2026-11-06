"""Verify primitive and fresh-process covariance receipts, then render the decision."""

import json
import shutil
import statistics
from pathlib import Path

import matplotlib
from probe_algo07v3_blas_threads import digest

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    out = Path(__file__).resolve().parent
    repo = out.parent.parent
    benchmark = repo / 'tools/benchmark_algo07v3_covariance_threads.py'
    old = out / 'measured-default-benchmark.py'
    originals = json.loads((out.parent / '2026_11_06_algo07v3_blas_threads' /
                           'receipts/both/result.json').read_bytes())['rows'][0]['cases']
    expected = {case: originals[index]['signature']
                for index, case in enumerate(('initial', 'recovery'))}
    receipts = out / 'receipts'
    receipts.mkdir(exist_ok=True)
    summaries = []

    def retain(root):
        data = json.loads((root / 'result.json').read_bytes())
        bindings = data.get('bindings', data.get('plan', {}).get('bindings'))
        for name, sha in bindings.items():
            path = Path(name)
            if path == benchmark and digest(path) != sha:
                path = old
            assert digest(path) == sha, name
        shutil.copyfile(root / 'result.json', receipts / f'{root.name}.json')
        return data

    primitive_rows = []
    for case in ('initial', 'recovery'):
        for threads in (2, 3):
            root = Path(f'/srv/bulk/leo-dev/algo07v3-blas-primitives-{case}-{threads}-20261106')
            data = retain(root)
            assert data['unchanged_trajectory_exact'] and data['expected'] == expected[case]
            primitive_rows.append(dict(case=case, threads=threads, rows=data['rows']))
        root = Path(f'/srv/bulk/leo-dev/algo07v3-covariance-threads-{case}-2-20261106')
        data = retain(root)
        assert data['exact'] and data['expected'] == expected[case]

    table = ['| Capture | Covariance threads / wait | Baseline wall s | Candidate wall s | '
             'Wall change | CPU change |', '| --- | --- | ---: | ---: | ---: | ---: |']
    for mode, threads in [('fresh', 2), ('fresh', 3), ('sleep', 2)]:
        for case in ('initial', 'recovery'):
            root = Path(f'/srv/bulk/leo-dev/algo07v3-covariance-{mode}-{case}-{threads}-20261106')
            data = retain(root)
            assert data['fresh_process_per_side']
            assert all(r['exact'] and r['expected'] == expected[case] for r in data['rows'])
            for row in data['rows']:
                for library in row['libraries']:
                    assert digest(Path(library['path'])) == library['sha256']
                if mode == 'sleep':
                    assert set(row['loaded_timeout_environment'].values()) == {4}
            grouped = {side: [r for r in data['rows'] if r['side'] == side]
                       for side in ('baseline', 'candidate')}
            assert all(len(rows) == 6 for rows in grouped.values())
            means = {side: {metric: statistics.mean(r[metric] for r in rows)
                            for metric in ('seconds', 'cpu_seconds')}
                     for side, rows in grouped.items()}
            ratios = {metric: means['candidate'][metric] / means['baseline'][metric]
                      for metric in ('seconds', 'cpu_seconds')}
            pairs = [grouped['candidate'][i]['seconds'] / grouped['baseline'][i]['seconds']
                     for i in range(6)]
            label = f"{threads} / {'short' if mode == 'sleep' else 'default'}"
            summaries.append(dict(case=case, setting=label, means=means, ratios=ratios,
                                  wall_pair_ratios=pairs, exact=True))
            table.append(f"| {case} | {label} | {means['baseline']['seconds']:.6f} | "
                         f"{means['candidate']['seconds']:.6f} | "
                         f"{100 * (ratios['seconds'] - 1):+.2f}% | "
                         f"{100 * (ratios['cpu_seconds'] - 1):+.2f}% |")
    (out / 'timings.md').write_text('\n'.join(table) + '\n')
    (out / 'summary.json').write_text(json.dumps(dict(
        primitives=primitive_rows, trials=summaries, adopted=False,
        production_modified=False, full_pipeline_speedup=None), indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), layout='constrained')
    labels = [f"{r['case']} · {r['setting']}" for r in summaries]
    positions = np.arange(len(summaries))
    for axis, metric, title in zip(
        axes, ('seconds', 'cpu_seconds'), ('Wall time', 'CPU time'), strict=True
    ):
        bars = axis.barh(positions, [r['ratios'][metric] for r in summaries], color='steelblue')
        axis.bar_label(bars, fmt='%.2fx', padding=3)
        axis.axvline(1, color='black', linestyle='--', label='Serial baseline')
        axis.set(yticks=positions, yticklabels=labels, xlabel='Candidate / matched baseline',
                 title=title, xlim=(0, 4.2))
        axis.invert_yaxis()
    for i, row in enumerate(summaries):
        axes[0].scatter(row['wall_pair_ratios'], np.full(6, i), s=20, color='darkorange',
                        zorder=3, label='Individual pairs' if i == 0 else None)
    axes[0].legend(loc='lower right')
    fig.suptitle('Covariance-only threading · exact captured-call outputs\n'
                 'Fresh processes; 6 alternating pairs × 3 calls per side; lower is better')
    fig.savefig(out / 'covariance-cost.png', dpi=150)
    plt.close(fig)
    print('\n'.join(table))


if __name__ == '__main__':
    main()
