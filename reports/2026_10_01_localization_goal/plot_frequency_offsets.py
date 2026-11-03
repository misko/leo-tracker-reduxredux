"""Descriptive offset disagreement; expose very unequal diagnostic coverage."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from regression_batch import digest

HERE = Path(__file__).resolve().parent


def main():
    path = HERE/'frequency-offset-coherence-v1.json'
    assert digest(path) == path.with_suffix('.sha256').read_text().strip()
    result = json.loads(path.read_text())
    fig, ax = plt.subplots(figsize=(8, 4.6), layout='constrained')
    for key, label in [
        ('receiver_channel', 'Same receiver/channel/RF'),
        ('receiver_channel_satellite', 'Also same inferred satellite'),
    ]:
        values = np.sort([v for g in result['groups'] if g['grouping'] == key
                          for v in g['donor_absolute_errors_hz']])
        ax.step(values, np.arange(1, len(values)+1)/len(values), where='post',
                label=f'{label} (n={len(values)})')
    ax.set_xscale('log')
    ax.set_xlabel('Absolute wrapped offset mismatch from other tracks (Hz)')
    ax.set_ylabel('Fraction of eligible tracks')
    ax.set_title('Fitted frequency offsets: descriptive donor disagreement')
    ax.legend(fontsize=8)
    ax.grid(alpha=.2)
    fig.text(.01, -.03, 'Different populations. Shared inference states; '
             'not held-out validation or oscillator calibration.', fontsize=9)
    fig.savefig(HERE/'frequency-offset-coherence-v1.png', dpi=160, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    main()
