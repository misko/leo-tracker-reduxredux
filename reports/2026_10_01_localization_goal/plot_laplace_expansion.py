"""Paired geographic changes from the sealed12-scan Laplace diagnostic."""
import json
from pathlib import Path

import matplotlib
import numpy as np
from regression_batch import digest

matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'nonlinear-laplace-expansion-v1-evaluation.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    data = json.loads(path.read_text())
    assert data['valid'] == data['planned'] == 12
    rows = data['rows']
    changes = np.array([r['error_m']-r['baseline_error_m'] for r in rows])
    fig, ax = plt.subplots(figsize=(9, 4.8), constrained_layout=True)
    ax.bar([r['unit'] for r in rows], changes,
           color=['#367c94' if c < 0 else '#bb704c' for c in changes])
    ax.axhline(0, color='gray', linewidth=1)
    ax.set(ylabel='Change in horizontal error (m); negative is better',
           title='Nonlinear Laplace correction: 3/12 improve; no promotion')
    ax.tick_params(axis='x', rotation=55)
    ax.spines[['top', 'right']].set_visible(False)
    fig.suptitle('Warm diagnostic: median 1,892 → 1,896 m; p90 3,998 → 4,046 m', fontsize=11)
    fig.savefig(HERE/'nonlinear-laplace-expansion-v1.png', dpi=150)


if __name__ == '__main__':
    main()
