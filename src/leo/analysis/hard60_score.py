"""Equivalent double-precision narrow-Gaussian score for the bounded cohort replay.

At sigma <= 1000 Hz, non-nearest wrapped images cannot affect the clutter-plus-
signal density in float64. Use the linear mixture directly, whose clutter floor
is strictly positive, to avoid allocating the three-image logsumexp tensor.
The deployed implementation remains the numerical oracle in tests/audits.
"""

import numpy as np

from leo.analysis.regional_position_score import (
    ALIAS_HZ,
    PositionObjective,
    WindowLikelihood,
    circular,
    observer,
    singleton_likelihood,
)


def likelihood(measured, prediction, visible, score):
    if score.sigma_hz > 1000:
        return singleton_likelihood(measured, prediction, visible, score)
    measured, prediction, visible = (
        np.asarray(measured),
        np.asarray(prediction),
        np.asarray(visible),
    )
    if (
        prediction.ndim != 2
        or measured.shape != (len(prediction),)
        or visible.shape != prediction.shape
        or visible.dtype != bool
        or not np.isfinite(measured).all()
        or not np.isfinite(prediction).all()
    ):
        raise ValueError("invalid singleton likelihood arrays")
    count = prediction.shape[1]
    if count <= score.detection_budget:
        raise ValueError("detection budget must be below satellite count")
    q = score.detection_budget / count
    residual = circular(measured[:, None] - prediction)
    signal = np.exp(-0.5 * (residual / score.sigma_hz) ** 2) * visible
    signal *= q / (1 - q) / (score.sigma_hz * np.sqrt(2 * np.pi))
    clutter = score.clutter_rate / ALIAS_HZ
    total = clutter + signal.sum(axis=1)
    log_p0 = -score.clutter_rate + visible.sum(axis=1) * np.log1p(-q)
    nll = -np.sum(log_p0 - np.log(-np.expm1(log_p0)) + np.log(total))
    responsibilities = signal / total[:, None]
    return WindowLikelihood(
        float(nll),
        responsibilities,
        clutter / total,
        -responsibilities * residual / score.sigma_hz**2,
        residual,
    )


class Hard60Objective(PositionObjective):
    def evaluate(self, vector):
        vector = np.asarray(vector, float)
        if vector.shape != (self.size,) or not np.isfinite(vector).all():
            raise ValueError("invalid position parameter vector")
        relative = self.basis @ vector[8:]
        prediction, visible, spatial, timing = predict_orbits(
            self.bank, self.observations, self.prior, vector[:2], vector[7] + relative
        )
        prediction += (self.design @ vector[2:7] + self.baseline)[:, None]
        terms = likelihood(self.observations.measured_hz, prediction, visible, self.score)
        weight = terms.prediction_gradient
        shift_gradient = np.sum(weight * timing, axis=0)
        gradient = np.zeros(self.size)
        gradient[:2] = np.einsum("nk,nki->i", weight, spatial)
        gradient[2:7] = self.design.T @ weight.sum(axis=1)
        gradient[7] = shift_gradient.sum() + vector[7] / self.score.common_sigma_s**2
        gradient[8:] = self.basis.T @ (shift_gradient + relative / self.score.relative_sigma_s**2)
        penalty = 0.5 * (vector[7] / self.score.common_sigma_s) ** 2
        penalty += 0.5 * np.sum((relative / self.score.relative_sigma_s) ** 2)
        return terms.nll + float(penalty), gradient, terms


def predict_orbits(bank, observations, prior, point, shifts_s, *, derivatives=True):
    """Use the packaged, audited kernel; never compile or fall back silently."""
    from leo.analysis import _regional_orbits

    shifts = np.ascontiguousarray(shifts_s, dtype=float)
    if shifts.shape != (len(bank.numbers),) or not np.isfinite(shifts).all():
        raise ValueError("one finite orbit shift per satellite required")
    site, up = observer(prior, point)
    jac = np.zeros((2, 3))
    if derivatives:
        eye = np.eye(2) * 0.001
        jac = np.stack(
            [
                (
                    observer(prior, np.asarray(point) + d)[0]
                    - observer(prior, np.asarray(point) - d)[0]
                )
                / 0.002
                for d in eye
            ]
        )
    prediction, visible, spatial, timing = _regional_orbits.predict(
        observations.times_s,
        observations.rf_hz,
        shifts,
        bank.position_km,
        bank.velocity_km_s,
        site,
        up,
        jac,
        bank.nodes_s[0],
        bank.nodes_s[1] - bank.nodes_s[0],
        derivatives,
    )
    return prediction, visible, spatial if derivatives else None, timing if derivatives else None
