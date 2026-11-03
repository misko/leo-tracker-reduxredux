"""Conditional local position information, with and without nuisance priors.

Candidate labels and noise assumptions are conditioned on, not validated here.
Outputs are optimistic local sensitivity measures, never empirical confidence.
"""

import numpy as np


def _profile(nuisance, position):
    norms = np.linalg.norm(nuisance, axis=0)
    nonzero = norms > 0
    scaled = nuisance[:, nonzero] / norms[nonzero]
    fitted = scaled @ np.linalg.lstsq(scaled, position, rcond=1e-10)[0]
    residual = position - fitted
    values = np.maximum(0, np.linalg.eigvalsh(residual.T @ residual))
    rank = int(np.sum(values > max(1e-14, values.max(initial=0) * 1e-10)))
    sigma = (1 / np.sqrt(values)).tolist() if rank == 2 else None
    return dict(
        position_rank=rank,
        information_eigenvalues_per_km2=values.tolist(),
        optimistic_axis_sigma_km=sigma,
        nuisance_rank=int(np.linalg.matrix_rank(scaled)),
    )


def conditional_position_information(
    fragments,
    *,
    fitted_c,
    phase_sigma_s=None,
    noise_hz=150.0,
    bias_sigma_hz=1000.0,
    drift_sigma_hz_s=2.0,
):
    if not fragments:
        return dict(status="no qualified curved anchors", empirical_confidence=False)
    if any(not f["active_curvature"] for f in fragments):
        raise ValueError("linear fragments cannot establish position/calibration information")
    phases = phase_sigma_s or {}
    components = sorted({f["component"] for f in fragments})
    satellites = sorted({f["satellite"] for f in fragments if f["satellite"] in phases})
    beta_size = 9 if fitted_c else 8
    component_index = {key: beta_size + i for i, key in enumerate(components)}
    phase_index = {key: beta_size + len(components) + i for i, key in enumerate(satellites)}
    counts = {
        key: sum(len(f["times"]) for f in fragments if f["component"] == key) for key in components
    }
    size = beta_size + len(components) + len(satellites)
    blocks, position_blocks = [], []
    for f in fragments:
        n = len(f["times"])
        features = np.zeros((n, size))
        g = f["group"]
        features[:, g] = 1
        features[:, g + 4] = (f["times"] - 150) / 150
        if fitted_c:
            features[:, 8] = f["rf_ratio"] * 11.5 - 11.5
        features[:, component_index[f["component"]]] = 1
        if f["satellite"] in phase_index:
            features[:, phase_index[f["satellite"]]] = f["phase_sensitivity_hz_s"]
        weight = np.sqrt(min(1.0, 50 / counts[f["component"]])) / noise_hz
        blocks.append(weight * features)
        position_blocks.append(weight * f["position_sensitivity_hz_km"])
    nuisance, position = np.concatenate(blocks), np.concatenate(position_blocks)
    priors = []
    for g in range(4):
        row = np.zeros(size)
        row[g + 4] = 1 / (150 * drift_sigma_hz_s)
        priors.append(row)
    for key, index in component_index.items():
        row = np.zeros(size)
        row[index] = np.sqrt(min(1.0, 50 / counts[key])) / bias_sigma_hz
        priors.append(row)
    for key, index in phase_index.items():
        if not np.isfinite(phases[key]) or phases[key] <= 0:
            raise ValueError("positive finite phase prior scale required")
        row = np.zeros(size)
        row[index] = 1 / phases[key]
        priors.append(row)
    prior_rows = np.asarray(priors)
    return dict(
        status="conditional local sensitivity",
        points=len(nuisance),
        components=len(components),
        phase_parameters=len(satellites),
        noise_hz=noise_hz,
        data_only=_profile(nuisance, position),
        with_declared_priors=_profile(
            np.vstack([nuisance, prior_rows]), np.vstack([position, np.zeros((len(prior_rows), 2))])
        ),
        empirical_confidence=False,
        satellite_identities_conditioned_on=True,
    )
