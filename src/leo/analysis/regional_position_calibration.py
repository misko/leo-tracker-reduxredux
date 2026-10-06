"""Full-window C0 nuisance calibration at a trial location, never a known roof."""

import time
from dataclasses import dataclass

import numpy as np

from leo.analysis.regional_position_fit import PositionFit, fit_position
from leo.analysis.regional_position_score import PositionObjective
from leo.contracts.regional_position import POSITION_SCORES


@dataclass(frozen=True)
class ReceiverCorrection:
    nodes_s: np.ndarray
    knots_hz: np.ndarray
    values_hz: np.ndarray
    support_rows: tuple[int, ...]


@dataclass(frozen=True)
class RegionalCalibration:
    satellite_indices: tuple[int, ...]
    prefit: PositionFit
    postfit: PositionFit
    correction: ReceiverCorrection
    receiver_baseline_hz: np.ndarray


def receiver_correction(observations, terms):
    """30-second piecewise-linear correction with constant/line knot gauges removed.

    Only high-responsibility, <=600 Hz rows train this nuisance correction. Those
    rows are not called held-out evidence; all windows remain in subsequent scores.
    """
    count = len(observations.window_ids)
    probability = terms.responsibilities
    if probability.ndim != 2 or probability.shape[0] != count or probability.shape[1] < 1:
        raise ValueError("invalid calibration responsibility shape")
    winner = probability.argmax(axis=1)
    rows = np.arange(count)
    support = (probability[rows, winner] >= 0.8) & (abs(terms.residual_hz[rows, winner]) <= 600)
    nodes = np.arange(
        np.floor(observations.times_s.min() / 30) * 30,
        np.ceil(observations.times_s.max() / 30) * 30 + 1,
        30,
    )
    if len(nodes) < 3:
        raise ValueError("scan too short for receiver correction")
    centered = nodes - nodes.mean()
    null = np.linalg.svd(
        np.stack([np.ones(len(nodes)), centered / max(abs(centered))]), full_matrices=True
    )[2][2:].T
    interpolation = np.column_stack(
        [np.interp(observations.times_s, nodes, row) for row in np.eye(len(nodes))]
    )
    design = interpolation @ null
    second = np.diff(np.eye(len(nodes)), n=2, axis=0) @ null
    precision = np.eye(null.shape[1]) / 50**2 + second.T @ second / 25**2
    coefficients = np.zeros((2, null.shape[1]))
    for rx in (0, 1):
        mask = support & (observations.receiver == rx)
        if mask.sum() < 10:
            raise ValueError("insufficient calibration support on a receiver")
        x = design[mask]
        y = terms.residual_hz[rows[mask], winner[mask]]
        weights = np.full(len(y), 1 / 200**2)
        for _ in range(3):
            beta = np.linalg.solve(x.T @ (weights[:, None] * x) + precision, x.T @ (weights * y))
            weights = np.minimum(1.0, 200 / np.maximum(abs(y - x @ beta), 1e-9)) / 200**2
        coefficients[rx] = beta
    values = np.sum(design * coefficients[observations.receiver], axis=1)
    return ReceiverCorrection(nodes, coefficients @ null.T, values, tuple(rows[support].tolist()))


def calibrate_position(observations, bank, prior, bootstrap, *, maximum_seconds=30.0):
    if not np.isfinite(maximum_seconds) or not 0 < maximum_seconds <= 1800:
        raise ValueError("invalid calibration time budget")
    begun = time.monotonic()
    selected = bank.select(list(bootstrap.satellite_indices))
    objective = PositionObjective(observations, selected, prior, POSITION_SCORES["T1AT"])
    prefit = fit_position(
        objective,
        bootstrap.vector,
        fixed_position=True,
        maximum_seconds=maximum_seconds / 2,
        maximum_iterations=200,
    )
    if not prefit.converged:
        raise ValueError("regional calibration prefit did not converge")
    terms = objective.evaluate(prefit.vector)[2]
    correction = receiver_correction(observations, terms)
    corrected = PositionObjective(
        observations,
        selected,
        prior,
        POSITION_SCORES["T1AT"],
        receiver_baseline_hz=correction.values_hz,
    )
    remaining = maximum_seconds - (time.monotonic() - begun)
    if remaining <= 0:
        raise TimeoutError("regional calibration time budget")
    postfit = fit_position(
        corrected,
        prefit.vector,
        fixed_position=True,
        maximum_seconds=remaining,
        maximum_iterations=200,
    )
    if not postfit.converged:
        raise ValueError("regional calibration postfit did not converge")
    baseline = correction.values_hz + corrected.design[:, :4] @ postfit.vector[2:6]
    return RegionalCalibration(bootstrap.satellite_indices, prefit, postfit, correction, baseline)
