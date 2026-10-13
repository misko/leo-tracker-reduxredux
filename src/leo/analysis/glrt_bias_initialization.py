"""Measured-track starts that retain source CFO separately from receiver calibration."""

import numpy as np

from leo.analysis.glrt_shape_initialization import shape_seeds


def bias_shape_seed(
    evidence,
    prediction,
    opportunity,
    tracks,
    calibration_hz,
    *,
    timing,
    phase_sigma_s=1.0,
    bias_sigma_hz=2000.0,
    maximum_satellites=40,
):
    calibration = np.asarray(calibration_hz, dtype=float)
    if (
        calibration.shape != evidence.time_s.shape
        or not np.isfinite(calibration).all()
        or not np.isfinite(bias_sigma_hz)
        or bias_sigma_hz <= 0
    ):
        raise ValueError("finite receiver calibration and positive source bias scale required")
    _, proposals = shape_seeds(
        evidence,
        prediction + calibration[:, None],
        opportunity,
        tracks,
        timing=timing,
        phase_sigma_s=phase_sigma_s,
        maximum_satellites=maximum_satellites,
    )
    accepted = []
    for proposal in proposals:
        bias = proposal["offset_hz"]
        if abs(bias) > 10 * bias_sigma_hz:
            continue
        support = min(proposal["support"], 100)
        prior = (bias / bias_sigma_hz) ** 2 + (proposal["phase_s"] / phase_sigma_s) ** 2
        weight = support / ((50 + proposal["rms_hz"]) ** 2 + 250**2 * prior / support)
        accepted.append(dict(proposal, bias_hz=bias, initialization_weight=float(weight)))
    if not accepted:
        raise ValueError("no bounded clock/shape proposals")
    support = {}
    for p in accepted:
        support[p["satellite"]] = support.get(p["satellite"], 0) + p["initialization_weight"]
    active = sorted(support, key=lambda s: (-support[s], s))[:maximum_satellites]
    bias, phase = np.zeros(prediction.shape[1]), np.zeros(prediction.shape[1])
    for sat in active:
        rows = [p for p in accepted if p["satellite"] == sat]
        weights = [p["initialization_weight"] for p in rows]
        bias[sat] = np.average([p["bias_hz"] for p in rows], weights=weights)
        phase[sat] = np.average([p["phase_s"] for p in rows], weights=weights)
    return dict(
        active=active, satellite_bias_hz=bias.tolist(), satellite_phase_s=phase.tolist()
    ), accepted
