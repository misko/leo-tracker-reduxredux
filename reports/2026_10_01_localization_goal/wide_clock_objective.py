"""Widen only the shared clock Gaussian prior; fixed baseline identities."""
import numpy as np
from fixed_reference_nuisance import ConditionalObjective

SIGMAS = {'control': 1., 'clock2': 2., 'clock5': 5.}
ARMS = tuple(SIGMAS)

class WideClockObjective(ConditionalObjective):
    def __init__(self, unit, arm):
        if arm not in SIGMAS:
            raise ValueError('unknown clock arm')
        super().__init__(unit, 'control')
        self.clock_sigma_s = SIGMAS[arm]
        self.precision[2] = 1 / self.clock_sigma_s**2
        self.columns = np.array([0, 1, 2, 3, 4, *self.epochs])
