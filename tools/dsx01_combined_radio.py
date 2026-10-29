"""Combine two separately tested radio hypotheses without changing observations."""

import numpy as np
from dsx01_independent_band_drift import independent_band_columns
from dsx01_window_noise import WindowNoise

VARIANTS = ("window_independent_2", "window_independent_10")


def replace_drift_columns(problem, sigma):
    groups = np.concatenate(
        [
            np.full(
                sl.stop - sl.start,
                2 * (problem.scan.tracks[i]["receiver"] - 1)
                + int(problem.scan.tracks[i]["channel"] > 4),
                dtype=int,
            )
            for i, sl in zip(problem.members, problem.slices, strict=True)
        ]
    )
    columns = independent_band_columns(groups, problem.flat_times, sigma)
    columns[:, [0, 2]] /= 10
    problem.hardware[:, 4:8] = columns


class CombinedRadio(WindowNoise):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown combined-radio hypothesis")
        self.band_sigma = float(variant.split("_")[-1])
        super().__init__(scan, seed, fitted_c, variant="window_noise", **kwargs)
        replace_drift_columns(self, self.band_sigma)

    def state(self, x):
        result = super().state(x)
        result["beta"][4:8] = self.calculate(x)["coefficient"][4:8] * self.band_sigma * 150
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            independent_RX_band_drift_sigma_hz_s=self.band_sigma,
            RX_low_high_drift_prior_correlation=0.0,
        )
        return result
