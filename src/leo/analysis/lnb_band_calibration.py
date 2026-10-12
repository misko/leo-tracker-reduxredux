"""Apply fixed learned receiver/band calibration through the observation port.

Subtracting gamma from measured CFO is exactly equivalent to adding gamma to
predicted CFO. This derived representation preserves every original window,
sample time, RF frequency and mark, and never changes persisted raw products.
"""

from dataclasses import replace

import numpy as np

from leo.contracts.regional_position import PositionObservations


def calibrated_band_observations(observations: PositionObservations, offsets_hz):
    offsets = np.asarray(offsets_hz, float)
    if offsets.shape != (2,) or not np.isfinite(offsets).all():
        raise ValueError("two finite receiver band offsets required")
    correction = offsets[observations.receiver] * (observations.channel >= 5)
    if not np.any(correction):
        return observations, correction
    return replace(observations, measured_hz=observations.measured_hz - correction), correction
