"""Paired accepted development errors with the original all-data baseline."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'alternating-expansion-v1-evaluation.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    result = json.loads(path.read_text())
    baseline_path = HERE/'candidate-joint-expansion-v1-evaluation.json'
    assert digest(baseline_path) == result['baseline_evaluation_sha256']
    baseline = {r['unit']: r for r in json.loads(baseline_path.read_text())['rows']
                if r['arm'] == 'candidate'}
    rows = [r for r in result['rows'] if r['arm'] == 'candidate']
    x = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(11, 5), layout='constrained')
    ax.scatter(x-.18, [baseline[r['unit']]['all_data_baseline_error_m'] for r in rows],
               label='Original all-data baseline', color='#777777')
    ax.scatter(x, [baseline[r['unit']]['error_m'] for r in rows],
               label='Fixed-identity joint model', color='#cb8a32')
    ax.scatter(x+.18, [r['error_m'] if r['valid'] else np.nan for r in rows],
               label='Alternating reassociation', color='#267eb2')
    ax.axhline(1000, color='black', linestyle=':', linewidth=.8)
    ax.axhline(3000, color='black', linestyle='--', linewidth=.8)
    ax.set_xticks(x, [r['unit'] for r in rows], rotation=40, ha='right')
    ax.set_ylim(bottom=0)
    ax.set_ylabel('Horizontal error (m)')
    ax.set_title('Frozen 12-scan development panel')
    ax.legend(fontsize=8)
    ax.grid(axis='y', alpha=.2)
    fig.text(.01, -.03, 'Warm development fits; candidate evidence used for training. '
             'No held-out or end-to-end timing claim.', fontsize=9)
    fig.savefig(HERE/'alternating-expansion-v1.png', dpi=160, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
