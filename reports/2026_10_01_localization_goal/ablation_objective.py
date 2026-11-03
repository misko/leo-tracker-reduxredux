"""Conditional complexity ablations with literal zero-fixed coordinates."""
import numpy as np

from fixed_reference_nuisance import ConditionalObjective

ARMS = ('control', 'no_clock', 'no_drift', 'no_epochs', 'position_only')


def retained_columns(dimension, epochs, arm):
    if arm not in ARMS:
        raise ValueError('unknown ablation')
    removed = {'control': [], 'no_clock': [2], 'no_drift': [3, 4],
               'no_epochs': list(range(5, dimension)),
               'position_only': list(range(2, dimension))}[arm]
    return np.array([k for k in [0, 1, 2, 3, 4, *epochs] if k not in removed]), removed


class AblationObjective(ConditionalObjective):
    def __init__(self, unit, arm):
        super().__init__(unit, 'control')
        self.columns, self.removed = retained_columns(len(self.initial), self.epochs, arm)
        self.initial[self.removed] = 0.
