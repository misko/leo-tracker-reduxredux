"""Offset-invariant Doppler trajectory inference, without storage or orbit imports.

Each supplied sequence is real, continuous receiver/channel support. Candidate
identity and ambiguity branch stay fixed over that sequence. Offsets are
profiled in whitened coordinates; adjacent differences are never treated as
independent measurements. Singleton sequences carry zero shape information.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from scipy.linalg import solve_triangular
from scipy.optimize import minimize


class OffsetProjector:
    """GLS projection of sequence constants, with optional declared RX drift."""

    def __init__(
        self,
        sequence_ids,
        *,
        sigma_hz=None,
        covariance_hz2=None,
        receiver_ids=None,
        times_s=None,
        shared_receiver_drift=False,
    ):
        ids = np.asarray(sequence_ids)
        if ids.ndim != 1 or len(ids) == 0:
            raise ValueError("nonempty one-dimensional sequence IDs required")
        if (sigma_hz is None) == (covariance_hz2 is None):
            raise ValueError("provide exactly one noise representation")
        self.size = len(ids)
        self.sequence_ids, inverse = np.unique(ids, return_inverse=True)
        design = np.eye(len(self.sequence_ids))[inverse]
        self.receiver_ids = ()
        if shared_receiver_drift:
            if receiver_ids is None or times_s is None:
                raise ValueError("shared receiver drift needs receiver IDs and times")
            receivers, times = np.asarray(receiver_ids), np.asarray(times_s, float)
            if receivers.shape != ids.shape or times.shape != ids.shape:
                raise ValueError("receiver/time shapes must match sequence IDs")
            if not np.all(np.isfinite(times)):
                raise ValueError("finite times required")
            self.receiver_ids, rx = np.unique(receivers, return_inverse=True)
            drift = np.eye(len(self.receiver_ids))[rx] * (times - np.mean(times))[:, None]
            design = np.column_stack((design, drift))
        self.design = design
        self._cholesky = None
        self._sigma = None
        if sigma_hz is not None:
            sigma = np.asarray(sigma_hz, float)
            if sigma.ndim == 0:
                sigma = np.full(self.size, float(sigma))
            if sigma.shape != ids.shape or not np.all(np.isfinite(sigma)) or np.any(sigma <= 0):
                raise ValueError("positive finite observation sigmas required")
            self._sigma = sigma
        else:
            covariance = np.asarray(covariance_hz2, float)
            if covariance.shape != (self.size, self.size) or not np.all(np.isfinite(covariance)):
                raise ValueError("finite square observation covariance required")
            if not np.allclose(covariance, covariance.T, rtol=1e-12, atol=1e-12):
                raise ValueError("symmetric covariance required")
            self._cholesky = np.linalg.cholesky(covariance)
        whitened = self.whiten(design)
        # SVD tolerates dependent drift columns and makes rank explicit.
        scale = np.linalg.norm(whitened, axis=0)
        normalized = whitened[:, scale > 0] / scale[scale > 0]
        u, singular, _ = np.linalg.svd(normalized, full_matrices=False)
        threshold = max(normalized.shape) * np.finfo(float).eps * singular[0]
        self.nuisance_rank = int(np.count_nonzero(singular > threshold))
        self._basis = u[:, : self.nuisance_rank]
        self._whitened_design = whitened
        self.shape_dof = self.size - self.nuisance_rank

    def whiten(self, values):
        values = np.asarray(values, float)
        if values.ndim not in (1, 2) or values.shape[0] != self.size:
            raise ValueError("values must have observations on their first axis")
        if not np.all(np.isfinite(values)):
            raise ValueError("finite values required")
        if self._sigma is not None:
            return values / (self._sigma if values.ndim == 1 else self._sigma[:, None])
        return solve_triangular(self._cholesky, values, lower=True)

    def project(self, values):
        whitened = self.whiten(values)
        return whitened - self._basis @ (self._basis.T @ whitened)

    def coefficients(self, residual_hz):
        """Training-only physical offset/drift coefficients for frozen prediction."""
        return np.linalg.lstsq(self._whitened_design, self.whiten(residual_hz), rcond=None)[0]

    def score(self, residual_hz):
        projected = self.project(residual_hz)
        return float(projected @ projected)

    def information(self, geo_jacobian_hz_per_km, nuisance_jacobian_hz=None):
        """Conditional horizontal information after offsets, timing and fitted c.

        This reports a local Gaussian bound, not position accuracy or identity
        certainty. Extra nuisance columns receive no assumed informative prior.
        """
        geometry = self.project(geo_jacobian_hz_per_km)
        nuisance_rank = 0
        if nuisance_jacobian_hz is not None:
            nuisance = self.project(nuisance_jacobian_hz)
            if nuisance.ndim != 2:
                raise ValueError("two-dimensional nuisance Jacobian required")
            scale = np.linalg.norm(nuisance, axis=0)
            nuisance = nuisance[:, scale > 1e-12] / scale[scale > 1e-12]
            if nuisance.shape[1]:
                u, singular, _ = np.linalg.svd(nuisance, full_matrices=False)
                threshold = max(nuisance.shape) * np.finfo(float).eps * singular[0]
                nuisance_rank = int(np.count_nonzero(singular > threshold))
                basis = u[:, :nuisance_rank]
                geometry -= basis @ (basis.T @ geometry)
        if geometry.ndim != 2:
            raise ValueError("two-dimensional geometry Jacobian required")
        singular = np.linalg.svd(geometry, compute_uv=False)
        threshold = (
            max(geometry.shape) * np.finfo(float).eps * (singular[0] if len(singular) else 0)
        )
        rank = int(np.count_nonzero(singular > threshold))
        full_rank = rank == geometry.shape[1]
        covariance = np.linalg.inv(geometry.T @ geometry) if full_rank else None
        return {
            "geo_rank": rank,
            "geo_parameters": geometry.shape[1],
            "singular_values_per_km": singular.tolist(),
            "condition": float(singular[0] / singular[-1]) if full_rank else None,
            "offset_drift_rank": self.nuisance_rank,
            "additional_nuisance_rank": nuisance_rank,
            "shape_dof": self.shape_dof,
            "conditional_covariance_km2": None if covariance is None else covariance.tolist(),
            "conditional_horizontal_rms_km": (
                None if covariance is None else float(np.sqrt(np.trace(covariance[:2, :2])))
            ),
        }


@dataclass(frozen=True)
class ShapeSequence:
    sequence_id: str
    observation_ids: tuple[str, ...]
    measured_hz: np.ndarray
    sigma_hz: np.ndarray
    candidate_branch_ids: tuple[str, ...]

    def projector(self):
        if len(self.observation_ids) != len(set(self.observation_ids)):
            raise ValueError("duplicate observations within sequence")
        if len(self.observation_ids) != len(self.measured_hz):
            raise ValueError("observation IDs and CFO must match")
        if not self.candidate_branch_ids or len(set(self.candidate_branch_ids)) != len(
            self.candidate_branch_ids
        ):
            raise ValueError("nonempty unique candidate/branch IDs required")
        return OffsetProjector(
            [self.sequence_id] * len(self.observation_ids), sigma_hz=self.sigma_hz
        )


def score_trajectory_bank(sequence: ShapeSequence, prediction_hz):
    """Score whole candidate branches; never select a branch per observation."""
    prediction = np.asarray(prediction_hz, float)
    expected = (len(sequence.candidate_branch_ids), len(sequence.measured_hz))
    if prediction.shape != expected:
        raise ValueError("candidate-by-observation prediction array required")
    projector = sequence.projector()
    residual = np.asarray(sequence.measured_hz)[None, :] - prediction
    projected = projector.project(residual.T)
    scores = np.sum(projected**2, axis=0)
    order = np.argsort(scores, kind="stable")
    chosen = int(order[0])
    return {
        "sequence_id": sequence.sequence_id,
        "candidate_branch_id": sequence.candidate_branch_ids[chosen],
        "candidate_index": chosen,
        "chi2": float(scores[chosen]),
        "runner_up_delta_chi2": float(scores[order[1]] - scores[chosen])
        if len(order) > 1
        else None,
        "candidate_chi2": scores.tolist(),
        "offset_hz": float(projector.coefficients(residual[chosen])[0]),
        "shape_dof": projector.shape_dof,
    }


def fit_shape_position(
    sequences: tuple[ShapeSequence, ...],
    predictor: Callable[[np.ndarray], tuple[np.ndarray, ...]],
    starts,
    bounds,
    *,
    max_iterations=150,
    prior: Callable[[np.ndarray], float] | None = None,
):
    """Bounded training-only optimization; theta may contain shared timing/c.

    Caller freezes observations, candidate bank, prior and starts for both c
    arms. A locked c=0 is omitted from theta. No reference coordinates enter.
    All stationary starts are retained; selection uses shape chi2 plus prior.
    """
    if not sequences or not any(sequence.projector().shape_dof for sequence in sequences):
        raise ValueError("no supported shape information")
    observations = [oid for sequence in sequences for oid in sequence.observation_ids]
    if len(observations) != len(set(observations)):
        raise ValueError("observation support must not overlap across sequences")

    def evaluate(theta):
        predictions = predictor(theta)
        if len(predictions) != len(sequences):
            raise ValueError("predictor must return one bank per sequence")
        rows = [score_trajectory_bank(s, p) for s, p in zip(sequences, predictions, strict=True)]
        penalty = 0.0 if prior is None else float(prior(theta))
        return sum(row["chi2"] for row in rows) + penalty, rows, penalty

    attempts = []
    for start in starts:
        result = minimize(
            lambda theta: evaluate(theta)[0],
            np.asarray(start, float),
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": max_iterations, "ftol": 1e-12, "gtol": 1e-6},
        )
        objective, rows, penalty = evaluate(result.x)
        attempts.append(
            {
                "theta": result.x.tolist(),
                "objective": float(objective),
                "shape_chi2": float(objective - penalty),
                "prior_penalty": penalty,
                "stationary": bool(result.success),
                "status": str(result.message),
                "iterations": int(result.nit),
                "evaluations": int(result.nfev),
                "sequences": rows,
            }
        )
    stationary = [row for row in attempts if row["stationary"]]
    return {
        "model": "offset-invariant-doppler-shape",
        "winner": min(stationary, key=lambda row: row["objective"]) if stationary else None,
        "attempts": attempts,
        "observation_count": len(observations),
        "sequence_count": len(sequences),
        "shape_dof": sum(s.projector().shape_dof for s in sequences),
    }
