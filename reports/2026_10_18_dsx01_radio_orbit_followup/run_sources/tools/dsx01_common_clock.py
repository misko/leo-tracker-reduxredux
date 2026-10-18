"""A common UTC uncertainty constrained by the original host query bracket."""

import numpy as np
from iterate_dsx01_position_nominations import AnchoredFamilies
from prototype_dsx01_pair_difference import PairDifferenceFamilies


class CommonClockMixin:
    def __init__(self, *args, clock, **kwargs):
        self.clock_size = None
        self.timing_parameters = 1
        self.clock = clock
        if not clock["lower_shift_s"] < clock["upper_shift_s"] or clock["sigma_s"] <= 0:
            raise ValueError("ordered physical time bracket and positive scale required")
        super().__init__(*args, **kwargs)
        self.clock_size = len(self.initial)
        self.initial = np.r_[self.initial, 0.0]
        self.lower = np.r_[
            self.lower, (clock["lower_shift_s"] - clock["mean_shift_s"]) / clock["sigma_s"]
        ]
        self.upper = np.r_[
            self.upper, (clock["upper_shift_s"] - clock["mean_shift_s"]) / clock["sigma_s"]
        ]

    def decode(self, x):
        if self.clock_size is None:
            return super().decode(x)
        state = super().decode(x[: self.clock_size])
        state["common_utc_shift_s"] = self.clock["mean_shift_s"] + x[-1] * self.clock["sigma_s"]
        return state

    def observation_times(self, state):
        return self.flat_times + state.get("common_utc_shift_s", 0.0)

    def residual(self, x, *, details=False):
        result = super().residual(x, details=details)
        r, diagnostics = result if details else (result, None)
        r = np.r_[r, x[-1]]
        return (r, diagnostics) if details else r


class CommonParentClock(CommonClockMixin, AnchoredFamilies):
    pass


class CommonPairClock(CommonClockMixin, PairDifferenceFamilies):
    pass
