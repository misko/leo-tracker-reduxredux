"""Controlled receiver-smooth frequency law; no new nuisance coordinates.

An additive oscillator contribution has the same CFO Hz across RF channels.
The incumbent instead scales that contribution by RF/11.5 GHz. This module
changes only the existing smooth receiver design, not orbital Doppler scaling,
measurements, labels, calibration eligibility or prior amplitude at 11.5 GHz.
"""

import copy
import numpy as np


def receiver_frequency_law(scan, law):
    if law not in ("fractional_RF", "additive_Hz"):
        raise ValueError("unknown receiver frequency law")
    changed = copy.copy(scan)
    changed.rx_basis = []
    for track, basis in zip(scan.tracks, scan.rx_basis, strict=True):
        q = track["rf_hz"] / 11.5e9
        if not np.isfinite(q) or q <= 0:
            raise ValueError("positive finite physical RF required")
        changed.rx_basis.append(np.array(basis, copy=True) / (q if law == "additive_Hz" else 1.))
    return changed
