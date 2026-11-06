"""Render every completed scalar-score trial, including regressions."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    record = json.loads((args.input / 'result.json').read_bytes())
    assert record['exact'] and len(record['rows']) == 48
    for name, sha in record['plan']['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    rows = record['rows']
    assert all(row['exact_score'] for row in rows)
    summary = []
    for size in sorted({row['phase_pairs'] for row in rows}):
        for mode in (True, False):
            group = [row for row in rows if row['phase_pairs'] == size
                     and row['optimize_contractions'] == mode]
            b = {r['repeat']: r for r in group if r['side'] == 'baseline'}
            c = {r['repeat']: r for r in group if r['side'] == 'candidate'}
            assert sorted(b) == sorted(c) == list(range(4))
            wall = [mean(v['seconds'] for v in side.values()) for side in (b, c)]
            cpu = [mean(v['cpu_seconds'] for v in side.values()) for side in (b, c)]
            summary.append(dict(phase_pairs=size, mode='optimized' if mode else 'direct',
                wall_seconds=wall, cpu_seconds=cpu, wall_reduction_pct=100 * (1-wall[1]/wall[0]),
                cpu_reduction_pct=100 * (1-cpu[1]/cpu[0]),
                faster_pairs=sum(c[i]['seconds'] < b[i]['seconds'] for i in b)))
    args.output.mkdir(exist_ok=True, parents=True)
    for name in ('plan.json', 'candidate.py', 'rows.json', 'result.json'):
        shutil.copy2(args.input / name, args.output / name)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    table = ['| Phase pairs | Mode | Full score, s | Scalar score, s | Wall reduction | '
             'CPU reduction | Faster pairs |',
             '| ---: | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in summary:
        b, c = row['wall_seconds']
        table.append(f"| {row['phase_pairs']:,} | {row['mode']} | {b:.6f} | {c:.6f} | "
                     f"{row['wall_reduction_pct']:+.2f}% | {row['cpu_reduction_pct']:+.2f}% | "
                     f"{row['faster_pairs']}/4 |")
    (args.output / 'timings.md').write_text('\n'.join(table) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    labels = [f"{r['phase_pairs']:,}\n{r['mode']}" for r in summary]
    for ax, key, title in zip(axes, ('wall_reduction_pct', 'cpu_reduction_pct'),
                              ('Elapsed time', 'CPU time'), strict=True):
        values = [r[key] for r in summary]
        ax.bar(np.arange(len(summary)), values,
               color=['#29825a' if v > 0 else '#ba5044' for v in values])
        ax.axhline(0, color='black', linewidth=.8)
        ax.set_xticks(np.arange(len(summary)), labels, rotation=40, ha='right', fontsize=8)
        ax.set_ylabel('Reduction relative to full diagnostic score (%)')
        ax.set_title(title)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Scalar-only joint score: four alternating pairs per grid and mode\n'
                 'Positive = faster; all 48 scores exact; no complete-pipeline claim')
    fig.savefig(args.output / 'runtime.png', dpi=150)
    plt.close(fig)
    print('\n'.join(table))


if __name__ == '__main__':
    main()
