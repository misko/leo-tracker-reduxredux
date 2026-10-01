"""Conditional model diagnostics and frozen correlation-time screen."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from screen_seed_prefix import sealed

HERE = Path(__file__).resolve().parent


def main():
    model = sealed(HERE/'added-evidence-model-check-v1.json')['rows']
    screen = sealed(HERE/'added-covariance-screen-v1.json')
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), constrained_layout=True)
    for ax, observed, simulated in ((axes[0], 'observed_standardized_rms', 'simulated_standardized_rms'),
                                    (axes[1], 'observed_sign_excess', 'simulated_sign_excess')):
        for i, row in enumerate(model):
            s = row[simulated]
            ax.errorbar(i, s['median'], yerr=[[s['median']-s['q025']], [s['q975']-s['median']]],
                        fmt='o', color='gray', capsize=5, label='Model 95% simulation range' if i == 0 else None)
            ax.scatter(i, row[observed], marker='x', s=65, color='tab:red', label='Observed' if i == 0 else None)
        ax.set_xticks(range(3), ['DS9', 'DS10', 'DS11'])
        ax.grid(alpha=.2)
    axes[0].set_ylabel('Conditional standardized residual RMS')
    axes[1].set_ylabel('Equal-sign pairs above within-track shuffle')
    axes[0].legend(fontsize=8)
    times = [.5, 2., 10., 60.]
    for unit, result in screen['totals'].items():
        scores = result['mean_scores']
        axes[2].plot(times, [scores[str(t)]-scores['0.5'] for t in times], marker='o', label=unit.split('-')[0])
    axes[2].set_xscale('log')
    axes[2].set_xticks(times, [str(t) for t in times])
    axes[2].set_xlabel('Correlation time (s); noise amplitudes fixed')
    axes[2].set_ylabel('Predictive gain per added observation (nats)')
    axes[2].legend()
    axes[2].grid(alpha=.2)
    fig.suptitle('Added-observation diagnostics at fixed eight-point states; no geographic refits')
    fig.savefig(HERE/'added-evidence-v1.png', dpi=160)


if __name__ == '__main__':
    main()
