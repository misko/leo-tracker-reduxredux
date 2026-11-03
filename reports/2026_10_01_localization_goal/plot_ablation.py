"""Display separately scoped complexity comparisons."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from regression_batch import digest

HERE = Path(__file__).resolve().parent
def read(name):
    path = HERE/name
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    return json.loads(path.read_text())

parameters = read('ablation-v1-evaluation.json')['summaries']
seeds = read('seed-count-ablation-v1.json')['summaries']
fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
for ax, values, labels, title in [
    (axes[0], list(seeds.values()), [f'{n} start(s)' for n in seeds], 'Search ablation: same64scans'),
    (axes[1], list(parameters.values()), ['Full model', 'No clock', 'No RX drift', 'No satellite timing', 'Position only'],
     'Conditional model ablation: same12scans')]:
    x = np.arange(len(values))
    ax.bar(x-.18, [r['median_error_m'] for r in values], .35, label='Median error')
    ax.bar(x+.18, [r['p90_error_m'] for r in values], .35, label='p90 error')
    ax.set_xticks(x, labels, rotation=25, ha='right')
    ax.set_title(title)
    ax.set_ylabel('Horizontal error (m), accepted results')
    ax.legend()
    for i, row in enumerate(values):
        ax.text(i, max(row['median_error_m'], row['p90_error_m']),
                f" {row['accepted']}/{row['planned']}", ha='center', va='bottom', fontsize=8)
fig.savefig(HERE/'ablation-v1.png', dpi=150)
