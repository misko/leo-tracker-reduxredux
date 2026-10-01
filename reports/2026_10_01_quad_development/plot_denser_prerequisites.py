"""Plot sealed prerequisite checks without a geographic performance claim."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from screen_seed_prefix import sealed

HERE = Path(__file__).resolve().parent


def main():
    ports = sealed(HERE/'denser-track-port-check-v1.json')['rows']
    scans = sealed(HERE/'denser-scan-objective-check-v1.json')['rows']
    assert [r['unit'] for r in ports] == [r['unit'] for r in scans]
    x = np.arange(3)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    axes[0].bar(x-.18, [r['points_8'] for r in ports], .36, label='Original 8-point cap')
    axes[0].bar(x+.18, [r['points_16'] for r in ports], .36, label='Nested 16-point cap')
    axes[0].set_ylabel('Retained observations in pilot scan')
    axes[0].legend()
    axes[1].bar(x, [r['maximum_gradient_error'] for r in scans])
    axes[1].axhline(.002, color='black', linestyle='--', label='Fixed check threshold')
    axes[1].set_yscale('log')
    axes[1].set_ylabel('Maximum directional derivative discrepancy')
    axes[1].legend()
    for ax in axes:
        ax.set_xticks(x, ['DS9', 'DS10', 'DS11'])
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Denser evidence prerequisites: exact 8-point control parity; no fits yet')
    fig.savefig(HERE/'denser-prerequisites-v1.png', dpi=160)


if __name__ == '__main__':
    main()
