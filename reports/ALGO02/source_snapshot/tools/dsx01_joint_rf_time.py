"""Transfer the earlier RF-times-time hypothesis into the current joint model.

This retains the corrected RX mean-drift priors and GLRT-300 point noise;
the earlier separate-nuisance RF-clock experiment is not rerun unchanged.
"""

import numpy as np
from dsx01_joint_marginal import JointMarginal
from dsx01_satellite_prior_controls import SatellitePriorControls

VARIANTS = ("rf_time_0p5", "rf_time_2")


def rf_time_columns(times, receivers, bands, rf_hz, centres, sigma):
    t, rx, band, rf = (np.asarray(v) for v in (times, receivers, bands, rf_hz))
    if (
        t.ndim != 1
        or any(v.shape != t.shape for v in (rx, band, rf))
        or sigma <= 0
        or not np.isfinite(t).all()
        or not np.isfinite(rf).all()
    ):
        raise ValueError("matching finite time/RF coordinates and positive scale required")
    result = np.zeros((len(t), 2))
    for r in (1, 2):
        for b in (0, 1):
            use = (rx == r) & (band == b)
            result[use, r - 1] = sigma * (rf[use] - centres[r, b]) / 1e9 * (t[use] - 150)
    return result


class JointRFTime(SatellitePriorControls):
    def __init__(self, scan, seed, fitted_c, *, variant, **kwargs):
        if variant not in VARIANTS:
            raise ValueError("unknown joint RF-times-time control")
        super().__init__(scan, seed, fitted_c, variant="normal", **kwargs)
        self.hypothesis = variant
        self.rf_time_sigma = 0.5 if variant == "rf_time_0p5" else 2.0
        groups = {}
        for track in scan.tracks:
            groups.setdefault((track["receiver"], int(track["channel"] > 4)), set()).add(
                track["rf_hz"]
            )
        centres = {key: float(np.mean(sorted(values))) for key, values in groups.items()}
        rx = np.concatenate(
            [
                np.full(sl.stop - sl.start, scan.tracks[i]["receiver"], int)
                for i, sl in zip(self.members, self.slices, strict=True)
            ]
        )
        band = np.concatenate(
            [
                np.full(sl.stop - sl.start, int(scan.tracks[i]["channel"] > 4), int)
                for i, sl in zip(self.members, self.slices, strict=True)
            ]
        )
        self.clock = rf_time_columns(
            self.flat_times, rx, band, self.q * 11.5e9, centres, self.rf_time_sigma
        )

    def state(self, x):
        result = JointMarginal.state(self, x)
        a = self.calculate(x)["coefficient"]
        begin = len(a) - len(self.members) - 2
        result["receiver_RF_rate_hz_s_ghz"] = a[begin : begin + 2] * self.rf_time_sigma
        return result

    def diagnostics(self, x):
        result = super().diagnostics(x)
        result.update(
            covariance_clock_columns=0,
            receiver_RF_rate_columns=2,
            receiver_RF_rate_sigma_hz_s_ghz=self.rf_time_sigma,
            RF_origins_use_recording_metadata_only=True,
        )
        return result
