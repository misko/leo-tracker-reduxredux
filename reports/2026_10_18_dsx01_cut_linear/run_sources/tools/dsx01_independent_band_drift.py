"""Four independent RX/band drift priors instead of a small band contrast.

This tests the hardware assumption directly. The baseline mean/contrast prior
strongly correlates the two band drifts on a receiver. No site truth is used.
"""

import numpy as np
from dsx01_robust_joint import RobustJoint

VARIANTS = ("independent_2", "independent_10")


def independent_band_columns(groups, times, sigma):
    g, t = np.asarray(groups), np.asarray(times, float)
    if (
        g.shape != t.shape
        or t.ndim != 1
        or not np.issubdtype(g.dtype, np.integer)
        or np.any(g < 0)
        or np.any(g > 3)
    ):
        raise ValueError("one RX/band group in [0,3] per sample required")
    if not np.isfinite(t).all() or not np.isfinite(sigma) or sigma <= 0:
        raise ValueError("finite times and positive drift prior sigma required")
    result = np.zeros((len(t), 4))
    result[np.arange(len(t)), g] = sigma * (t - 150)
    return result


class IndependentBands(RobustJoint):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown independent-band control")
        self.band_sigma = float(variant.split("_")[-1])
        super().__init__(scan, seed, fitted_c, variant="robust", **kwargs)
        group = np.concatenate(
            [
                np.full(
                    sl.stop - sl.start,
                    2 * (scan.tracks[i]["receiver"] - 1) + int(scan.tracks[i]["channel"] > 4),
                    dtype=int,
                )
                for i, sl in zip(self.members, self.slices, strict=True)
            ]
        )
        columns = independent_band_columns(group, self.flat_times, self.band_sigma)
        # The parent multiplies coordinates 4 and 6 by its RX-mean sigma 10.
        # Cancel that coordinate scale so all four columns are independent.
        columns[:, [0, 2]] /= 10
        self.hardware[:, 4:8] = columns

    def state(self, x):
        result = super().state(x)
        result["beta"][4:8] = self.calculate(x)["coefficient"][4:8] * self.band_sigma * 150
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            independent_RX_band_drift_sigma_hz_s=self.band_sigma,
            RX_low_high_drift_prior_correlation=0.0,
            rx_drift_mean_sigma_hz_s=self.band_sigma / np.sqrt(2),
            rx_drift_band_contrast_sigma_hz_s=self.band_sigma / np.sqrt(2),
        )
        return result
