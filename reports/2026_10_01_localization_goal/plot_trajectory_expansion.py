"""Compare cold geography and separately decomposed checking evidence."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'trajectory-expansion-v1-evaluation.json'
    decomposition = HERE/'trajectory-expansion-checking-decomposition-v1.json'
    for p in [path, decomposition]:
        assert digest(p) == p.with_suffix('.sha256').read_text().strip()
    rows = json.loads(path.read_text())['rows']
    scores = {r['unit']: r for r in json.loads(decomposition.read_text())['rows']}
    fig, axes = plt.subplots(2, 1, figsize=(11, 8), sharex=True, layout='constrained')
    x = np.arange(len(rows))
    for offset, key, label in [
        (-.18, 'original_all_data_error_m', 'Original all-data baseline'),
        (0, 'chronological_split_error_m', 'Chronological split training'),
        (.18, 'error_m', 'First-ranked trajectory hypothesis'),
    ]:
        axes[0].scatter(x+offset, [r.get(key, np.nan) if r['accepted'] else np.nan for r in rows],
                        label=label, s=35)
    axes[0].set_ylabel('Horizontal error (m)')
    axes[0].axhline(1000, linestyle=':', color='black', linewidth=.8)
    axes[0].axhline(3000, linestyle='--', color='black', linewidth=.8)
    axes[0].legend(fontsize=8)
    for i, r in enumerate(rows):
        if not r['accepted']:
            axes[0].text(i, 0, 'Failed', rotation=90, ha='center')
    total = [scores[r['unit']].get('total_gain', np.nan) for r in rows]
    common = [scores[r['unit']].get('sections', {}).get('common', {}).get(
        'log_ratio_gain', np.nan) for r in rows]
    axes[1].bar(x-.18, total, width=.36, label='All checking groups')
    axes[1].bar(x+.18, common, width=.36, label='Groups predicted by both models')
    axes[1].axhline(0, color='black', linewidth=.8)
    axes[1].set_ylabel('Checking log-score gain (nats)')
    axes[1].legend(fontsize=8)
    axes[1].set_xticks(x, [r['unit'] for r in rows], rotation=40, ha='right')
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Fixed 12-scan development panel: alternative trajectory selection')
    fig.text(.01, -.025, 'Composite checking scores are not geographic accuracy. '
             'Three sealed pilots reused; nine additional cold fits. Development data.', fontsize=9)
    fig.savefig(HERE/'trajectory-expansion-v1.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
