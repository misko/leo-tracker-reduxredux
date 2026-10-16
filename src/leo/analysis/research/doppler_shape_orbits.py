"""Bounded orbit-backed Model B using verified, branch-continuous sequences."""

from __future__ import annotations

import time

import numpy as np
from scipy.optimize import minimize, nnls
from scipy.special import logsumexp

from leo.analysis.regional_position_score import predict_orbits
from leo.analysis.research.doppler_shape_model import OffsetProjector


class DopplerShapeOrbitObjective:
    """Profile one offset and one satellite identity per supported sequence.

    Rows must already be unwrapped along an evidence-supported ambiguity
    branch. The objective never wraps individual residuals, joins across gaps,
    or treats correlated adjacent differences as independent. The candidate
    bank stays fixed. A common orbit shift is the declared lean timing model.
    RF c uses Hz/GHz; per-channel offsets annihilate its constant part exactly.
    """

    def __init__(self, observations, bank, prior, sequences, *, sigma_hz=400.0, timing_sigma_s=2.0):
        self.observations, self.bank, self.prior = observations, bank, prior
        self.sigma_hz, self.timing_sigma_s = sigma_hz, timing_sigma_s
        self.sequences = tuple(np.asarray(rows, int) for rows in sequences)
        all_rows = np.concatenate(self.sequences) if self.sequences else np.array([], int)
        if len(all_rows) != len(set(all_rows.tolist())) or np.any(all_rows < 0):
            raise ValueError("disjoint nonnegative sequence rows required")
        if len(all_rows) == 0 or np.any(all_rows >= len(observations.window_ids)):
            raise ValueError("supported observation rows required")
        if any(len(rows) < 2 for rows in self.sequences):
            raise ValueError("each shape sequence needs at least two observations")
        self.projectors = tuple(
            OffsetProjector(np.zeros(len(r)), sigma_hz=sigma_hz) for r in self.sequences
        )
        self.rf_design = (observations.rf_hz - observations.rf_center_hz) / 1e9
        self.c_shape_norm = float(
            np.sqrt(
                sum(
                    np.sum(p.project(self.rf_design[r]) ** 2)
                    for p, r in zip(self.projectors, self.sequences, strict=True)
                )
            )
        )

    def evaluate(self, theta, *, fitted_c=False, details=False):
        theta = np.asarray(theta, float)
        if theta.shape != (4 if fitted_c else 3,):
            raise ValueError("theta is east,north,common timing[,c]")
        pred, visible, spatial, timing = predict_orbits(
            self.bank,
            self.observations,
            self.prior,
            theta[:2],
            np.full(len(self.bank.numbers), theta[2]),
        )
        if fitted_c:
            pred = pred + theta[3] * self.rf_design[:, None]
        value, gradient, choices = 0.0, np.zeros(len(theta)), []
        for rows, projector in zip(self.sequences, self.projectors, strict=True):
            residual = self.observations.measured_hz[rows, None] - pred[rows]
            projected = projector.project(residual)
            scores = 0.5 * np.sum(projected**2, axis=0)
            allowed = np.all(visible[rows], axis=0)
            scores[~allowed] = np.inf
            if not np.any(allowed):
                return (1e15, np.zeros(len(theta)), []) if details else (1e15, np.zeros(len(theta)))
            selected = int(np.argmin(scores))
            weight = -projected[:, selected]
            gradient[:2] += projector.project(spatial[rows, selected]).T @ weight
            gradient[2] += projector.project(timing[rows, selected]) @ weight
            if fitted_c:
                gradient[3] += projector.project(self.rf_design[rows]) @ weight
            value += float(scores[selected])
            if details:
                order = np.argsort(scores)
                probabilities = np.exp(-scores - logsumexp(-scores))
                positive = probabilities > 0
                choices.append(
                    {
                        "rows": rows.tolist(),
                        "satellite_number": int(self.bank.numbers[selected]),
                        "satellite_index": selected,
                        "offset_hz": float(projector.coefficients(residual[:, selected])[0]),
                        "shape_chi2": float(2.0 * scores[selected]),
                        "selected_conditional_probability": float(probabilities[selected]),
                        "conditional_identity_entropy_nats": float(
                            -np.sum(probabilities[positive] * np.log(probabilities[positive]))
                        ),
                        "top_candidate_numbers": [int(self.bank.numbers[i]) for i in order[:5]],
                        "runner_up_delta_chi2": (
                            float(2.0 * (scores[order[1]] - scores[selected]))
                            if len(order) > 1 and np.isfinite(scores[order[1]])
                            else None
                        ),
                    }
                )
        value += 0.5 * (theta[2] / self.timing_sigma_s) ** 2
        gradient[2] += theta[2] / self.timing_sigma_s**2
        return (float(value), gradient, choices) if details else (float(value), gradient)

    def information(self, theta, *, fitted_c=False):
        _, _, choices = self.evaluate(theta, fitted_c=fitted_c, details=True)
        _, _, spatial, timing = predict_orbits(
            self.bank,
            self.observations,
            self.prior,
            np.asarray(theta)[:2],
            np.full(len(self.bank.numbers), theta[2]),
        )
        rows = np.concatenate(self.sequences)
        ids = np.concatenate([np.full(len(r), i) for i, r in enumerate(self.sequences)])
        projector = OffsetProjector(ids, sigma_hz=self.sigma_hz)
        geo = np.concatenate(
            [spatial[r, c["satellite_index"]] for r, c in zip(self.sequences, choices, strict=True)]
        )
        nuisance = np.concatenate(
            [timing[r, c["satellite_index"]] for r, c in zip(self.sequences, choices, strict=True)]
        )[:, None]
        if fitted_c:
            nuisance = np.column_stack((nuisance, self.rf_design[rows]))
        return projector.information(geo, nuisance)


def fit_doppler_shape(
    objective, starts, *, rf_arm="zero-c", maximum_seconds=45.0, maximum_iterations=600
):
    """Fit matched starts and disk/timing bounds. Return explicit timed failures."""
    if rf_arm not in ("zero-c", "fitted-c"):
        raise ValueError("unknown RF arm")
    fitted_c = rf_arm == "fitted-c"
    lower_t = max(-10.0, objective.bank.nodes_s[0] - objective.observations.times_s.min())
    upper_t = min(10.0, objective.bank.nodes_s[-1] - objective.observations.times_s.max())
    radius = objective.prior.radius_km
    bounds = [(-radius, radius), (-radius, radius), (lower_t, upper_t)]
    if fitted_c:
        bounds.append((-5000.0, 5000.0))
    attempts = []
    for start in starts:
        initial = np.r_[np.asarray(start, float)[:2], 0.0]
        if fitted_c:
            initial = np.r_[initial, 0.0]
        begun = time.monotonic()
        best = None

        def evaluate(theta, begun=begun):
            nonlocal best
            if time.monotonic() - begun >= maximum_seconds:
                raise TimeoutError("shape fit deadline")
            result = objective.evaluate(theta, fitted_c=fitted_c)
            if np.linalg.norm(theta[:2]) <= radius + 1e-6 and (best is None or result[0] < best[0]):
                best = result[0], theta.copy(), result[1].copy()
            return result

        result, reason = None, "time-limit"
        try:
            result = minimize(
                evaluate,
                initial,
                jac=True,
                method="SLSQP",
                bounds=bounds,
                constraints={
                    "type": "ineq",
                    "fun": lambda x: radius**2 - x[:2] @ x[:2],
                    "jac": lambda x: np.r_[-2.0 * x[:2], np.zeros(len(x) - 2)],
                },
                options={"maxiter": maximum_iterations, "ftol": 1e-9},
            )
            reason = str(result.message)
        except TimeoutError:
            pass
        theta = initial if best is None else best[1]
        if result is not None and result.success:
            theta = result.x
        value, gradient, choices = objective.evaluate(theta, fitted_c=fitted_c, details=True)
        normals = []
        for index, (lower, upper) in enumerate(bounds):
            unit = np.eye(len(theta))[index]
            if theta[index] <= lower + 1e-5:
                normals.append(unit)
            if theta[index] >= upper - 1e-5:
                normals.append(-unit)
        if np.linalg.norm(theta[:2]) >= radius - 1e-5:
            normals.append(np.r_[-theta[:2] / radius, np.zeros(len(theta) - 2)])
        stationarity = float(np.linalg.norm(gradient, ord=np.inf))
        if normals:
            matrix = np.asarray(normals).T
            multipliers = nnls(matrix, gradient)[0]
            stationarity = float(np.linalg.norm(gradient - matrix @ multipliers, ord=np.inf))
        feasible = np.linalg.norm(theta[:2]) <= radius + 1e-5 and all(
            lower - 1e-6 <= value <= upper + 1e-6
            for value, (lower, upper) in zip(theta, bounds, strict=True)
        )
        converged = bool(
            result is not None
            and result.success
            and stationarity <= 1e-3
            and feasible
            and len(choices) == len(objective.sequences)
            and value < 1e15
        )
        attempts.append(
            {
                "theta": theta.tolist(),
                "objective": value,
                "stationary": converged,
                "stationarity": stationarity,
                "status": reason,
                "gradient_norm": float(np.linalg.norm(gradient)),
                "elapsed_s": time.monotonic() - begun,
                "sequences": choices,
            }
        )
    stationary = [a for a in attempts if a["stationary"]]
    winner = min(stationary, key=lambda a: a["objective"]) if stationary else None
    if winner is not None:
        winner["information"] = objective.information(winner["theta"], fitted_c=fitted_c)
        shape_chi2 = sum(sequence["shape_chi2"] for sequence in winner["sequences"])
        winner["training_shape_rms_hz"] = float(
            objective.sigma_hz * np.sqrt(shape_chi2 / sum(map(len, objective.sequences)))
        )
    return {
        "model": "offset-invariant-doppler-shape",
        "rf_arm": rf_arm,
        "winner": winner,
        "attempts": attempts,
        "c_projected_design_norm": objective.c_shape_norm,
        "sequence_count": len(objective.sequences),
        "observation_count": sum(map(len, objective.sequences)),
        "shape_dof": sum(p.shape_dof for p in objective.projectors),
    }


def held_shape_score(objective, theta, held_objective, *, fitted_c=False):
    """Frozen-bank predictive mixture on held shape contrasts, with no held fit.

    Unknown per-sequence constants are removed as part of the measurement
    definition. Candidate weights come from training sequence assignments;
    held sequences do not select a new satellite, clock, timing or position.
    This is not comparable numerically with absolute-window frequency NLL.
    """
    _, _, choices = objective.evaluate(theta, fitted_c=fitted_c, details=True)
    counts = np.ones(len(objective.bank.numbers))
    for choice in choices:
        counts[choice["satellite_index"]] += 1.0
    log_weights = np.log(counts / counts.sum())
    pred, visible, _, _ = predict_orbits(
        held_objective.bank,
        held_objective.observations,
        held_objective.prior,
        np.asarray(theta)[:2],
        np.full(len(held_objective.bank.numbers), theta[2]),
        derivatives=False,
    )
    if fitted_c:
        pred += theta[3] * held_objective.rf_design[:, None]
    nll, dof, rows_count = 0.0, 0, 0
    for rows, projector in zip(held_objective.sequences, held_objective.projectors, strict=True):
        projected = projector.project(
            held_objective.observations.measured_hz[rows, None] - pred[rows]
        )
        log_density = -0.5 * np.sum(projected**2, axis=0)
        log_density -= 0.5 * projector.shape_dof * np.log(2.0 * np.pi * objective.sigma_hz**2)
        log_density[~np.all(visible[rows], axis=0)] = -np.inf
        nll -= float(logsumexp(log_density + log_weights))
        dof += projector.shape_dof
        rows_count += len(rows)
    return {
        "shape_nll": nll if np.isfinite(nll) else None,
        "shape_dof": dof,
        "shape_nll_per_dof": nll / dof if dof and np.isfinite(nll) else None,
        "observation_count": rows_count,
        "sequence_count": len(held_objective.sequences),
        "likelihood": "training-weighted-fixed-bank-projected-gaussian-mixture",
        "failure": None if np.isfinite(nll) else "held-sequence-has-no-visible-bank-candidate",
    }
