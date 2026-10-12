"""Explicit receiver-specific high-band offsets around the shared-track model.

Offsets act on predicted physical CFO in Hz, before any alias wrapping. They
are distinct from the RF stretch coefficient and its time evolution. Existing
RF-drift coefficients remain the final two clock entries so c=0 locks preserve
their established meaning. No published observation or recording is modified.
"""

import numpy as np

from leo.analysis.shared_track_objective import SharedTrackObjective


class LnbBandObjective(SharedTrackObjective):
    def __init__(
        self,
        base,
        nodes,
        knots,
        centers_s,
        groups,
        *,
        shared_prior=0.0,
        enabled=True,
        band_sigma_hz=25000.0,
        band_scale=25.0,
    ):
        if (
            not np.isfinite((band_sigma_hz, band_scale)).all()
            or min(band_sigma_hz, band_scale) <= 0
        ):
            raise ValueError("band prior and numerical scale must be finite and positive")
        super().__init__(base, nodes, knots, centers_s, groups, shared_prior=shared_prior)
        self.band_sigma_hz, self.band_scale = band_sigma_hz, band_scale
        self.parent_clock_count = len(self.initial_clock)
        high = self.observations.channel >= 5
        self.active_band_receivers = tuple(
            receiver
            for receiver in (0, 1)
            if enabled
            and np.any(high & (self.observations.receiver == receiver))
            and np.any(~high & (self.observations.receiver == receiver))
        )
        count = len(self.active_band_receivers)
        insertion = self.parent_clock_count - 2
        self.band_slice = slice(insertion, insertion + count)
        if not count:
            return
        indices = np.r_[np.arange(insertion), np.arange(insertion + count, insertion + count + 2)]
        precision = np.zeros((self.parent_clock_count + count,) * 2)
        precision[np.ix_(indices, indices)] = self.precision
        precision[self.band_slice, self.band_slice] = (
            np.eye(count) / (band_sigma_hz / band_scale) ** 2
        )
        design = np.zeros((len(self.observations.times_s), len(precision)))
        design[:, indices] = self.clock_design
        design[:, self.band_slice] = np.column_stack(
            [
                band_scale * high * (self.observations.receiver == receiver)
                for receiver in self.active_band_receivers
            ]
        )
        self.precision, self.clock_design = precision, design
        self.initial_clock = np.r_[
            self.initial_clock[:-2], np.zeros(count), self.initial_clock[-2:]
        ]

    def expand_parent_clock(self, clock, offsets_hz=(0.0, 0.0)):
        clock, offsets = np.asarray(clock, float), np.asarray(offsets_hz, float)
        if clock.shape != (self.parent_clock_count,) or offsets.shape != (2,):
            raise ValueError("invalid parent clock or receiver-band offsets")
        if not np.isfinite(clock).all() or not np.isfinite(offsets).all():
            raise ValueError("nonfinite parent clock or receiver-band offsets")
        added = offsets[list(self.active_band_receivers)] / self.band_scale
        return np.r_[clock[:-2], added, clock[-2:]]

    def band_offsets_hz(self, clock):
        clock = np.asarray(clock, float)
        if clock.shape != self.initial_clock.shape or not np.isfinite(clock).all():
            raise ValueError("invalid band-model clock coefficients")
        result = np.zeros(2)
        result[list(self.active_band_receivers)] = clock[self.band_slice] * self.band_scale
        return result
