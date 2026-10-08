"""Change only the Gaussian satellite-slope precision in the frozen model."""

import numpy as np
from satellite_correction import SatelliteCorrection


class SlopePrior(SatelliteCorrection):
    def __init__(self, base, nodes, knots, centers_s, sigma_hz_s):
        if not np.isfinite(sigma_hz_s) or sigma_hz_s <= 0:
            raise ValueError("Positive finite slope sigma required")
        super().__init__(base, nodes, knots, centers_s, "slope")
        count = self.slope_slice.stop - self.slope_slice.start
        self.precision[self.slope_slice, self.slope_slice] = np.eye(count) / (100 * sigma_hz_s) ** 2
