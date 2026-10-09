"""Illustrate missing label information; no recording inputs or position results."""

from pathlib import Path

import numpy as np
from matplotlib.figure import Figure

from mixture_curvature import curvature

HERE = Path(__file__).resolve().parent


def main():
    locations = np.linspace(-4, 4, 401)
    cost, complete, observed = [], [], []
    for x in locations:
        predictions = np.array([[x - 2, x + 2]])
        likelihood = np.exp(-0.5 * predictions**2)
        probability = likelihood / likelihood.sum()
        result = curvature(np.ones((1, 2, 1)), -predictions, probability, 1.0)
        cost.append(-np.log(0.5 * likelihood.sum()))
        complete.append(result['complete'][0, 0])
        observed.append(result['observed_local'][0, 0])
    figure = Figure(figsize=(10, 4), layout='constrained')
    left, right = figure.subplots(1, 2)
    left.plot(locations, cost, color='#176b91')
    left.set(xlabel='Synthetic scalar parameter', ylabel='Negative log likelihood',
             title='Two competing Gaussian hypotheses')
    right.plot(locations, complete, label='Frozen-label information', color='#b17817')
    right.plot(locations, observed, label='Observed mixture curvature', color='#176b91')
    right.axhline(0, color='gray', linewidth=0.8)
    right.set(xlabel='Synthetic scalar parameter', ylabel='Local curvature',
              title='Ambiguity removes information')
    right.legend()
    figure.suptitle('Synthetic illustration only — no scan or position-error results')
    figure.savefig(HERE / 'synthetic-ambiguity.png', dpi=160)


if __name__ == '__main__':
    main()
