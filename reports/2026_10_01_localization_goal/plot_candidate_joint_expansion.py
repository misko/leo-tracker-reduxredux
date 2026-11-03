"""Plot audited, paired development errors; retain failed spatial fits visibly."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'candidate-joint-expansion-v1-evaluation.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    evaluation = json.loads(path.read_text())
    rows = [r for r in evaluation['rows'] if r['arm'] == 'candidate']
    spatial_path = HERE/'candidate-spatial-expansion-v1-evaluation.json'
    assert digest(spatial_path) == evaluation['spatial_evaluation_sha256']
    spatial = {r['unit']: r for r in json.loads(spatial_path.read_text())['rows']
               if r['arm'] == 'candidate'}
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(12, 5.5), layout='constrained')
    series = [
        ('Original all-data baseline', 'all_data_baseline_error_m', -.24, '#666666'),
        ('Split training', 'baseline_error_m', -.08, '#d98b25'),
        ('Joint candidate model', 'error_m', .24, '#2577b5'),
    ]
    for label, key, offset, color in series:
        values = [r[key] if r[key] is not None else np.nan for r in rows]
        ax.scatter(x+offset, values, label=label, color=color, s=36)
    values = [spatial[r['unit']]['error_m'] if spatial[r['unit']]['valid']
              else np.nan for r in rows]
    ax.scatter(x+.08, values, label='Position-only candidate model', color='#48a077', s=36)
    for i, row in enumerate(rows):
        if not spatial[row['unit']]['valid']:
            ax.text(i, 110, 'Spatial fit failed', rotation=90, fontsize=8, ha='center')
    ax.axhline(1000, color='black', linewidth=.8, linestyle=':')
    ax.axhline(3000, color='black', linewidth=.8, linestyle='--')
    ax.set_xticks(x, [r['unit'] for r in rows], rotation=40, ha='right')
    ax.set_ylabel('Horizontal error (m)')
    ax.set_ylim(bottom=0)
    ax.set_title('Frozen 12-scan development panel — paired localization errors')
    ax.legend(fontsize=8, ncols=2)
    ax.grid(axis='y', alpha=.2)
    fig.text(.01, -.035, 'Warm fits with fixed identities; '
             'candidate observations used for fitting. '
             'No held-out accuracy or end-to-end runtime claim.', fontsize=9)
    fig.savefig(HERE/'candidate-joint-expansion-v1.png', dpi=160, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
