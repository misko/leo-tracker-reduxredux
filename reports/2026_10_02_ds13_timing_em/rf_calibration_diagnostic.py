"""Joint RF-dependent calibration ablation with the unchanged soft GLRT likelihood."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from finite_set_fit import assert_snapshot_unchanged, snapshot_files
from finite_set_likelihood import prepare_finite_set_likelihood
from prepare_scans import ROOT, load_scan
from rough_smoke import serializable
from soft_likelihood import SoftLikelihood
from soft_solvers import _fisher_system, _project_bounds, _scaled_projected_gradient
from solvers import _optimizer_scale
from timing_model import DeadlineReached, TimingObjective


def rf_features(rf, receiver, separate):
    rf = np.asarray(rf, dtype=float)
    receiver = np.asarray(receiver)
    center = float(np.mean(np.unique(rf)))
    frequency = (rf - center) / 1e9
    features = (np.column_stack([frequency * (receiver == index) for index in (0, 1)])
                if separate else frequency[:, None])
    return center, features


class CalibratedLikelihood(SoftLikelihood):
    def __init__(self, prepared, probability, features):
        super().__init__(prepared, probability)
        self.features = features
        self.coefficients = np.zeros(features.shape[1])

    def evaluate(self, predicted, visible, **options):
        return super().evaluate(predicted + (self.features @ self.coefficients)[:, None],
                                visible, **options)


class CalibrationObjective:
    def __init__(self, data, initial, satellites, separate, budget_s):
        self.started = time.monotonic()
        self.center, self.features = rf_features(data.rf, data.receiver, separate)
        prepared = prepare_finite_set_likelihood(data.measured, data.group)
        self.likelihood = CalibratedLikelihood(prepared, 0.8 / len(satellites), self.features)
        self.base = TimingObjective(data, initial, satellites, self.likelihood, 200.,
                                    deadline=self.started + budget_s)
        self.size = len(self.base.initial_vector)
        self.initial = np.r_[self.base.initial_vector, self.likelihood.coefficients]
        self.bounds = self.base.bounds + [(-5000., 5000.)] * self.features.shape[1]
        self.scale = np.r_[_optimizer_scale(self.size), np.full(self.features.shape[1], 1000.)]
        self.best = None

    def evaluate(self, vector):
        self.likelihood.coefficients = np.asarray(vector[self.size:]).copy()
        value, gradient = self.base.evaluate(vector[:self.size])
        if self.base.last is None:
            return value, np.r_[gradient, np.zeros(self.features.shape[1])]
        frequency_gradient = -self.likelihood.last_result["prediction_gradient"].sum(axis=1)
        gradient = np.r_[gradient, self.features.T @ frequency_gradient]
        if self.best is None or value < self.best["objective"]:
            self.best = {"objective": value, "vector": vector.copy(), "gradient": gradient.copy()}
        return value, gradient

    def curvature(self, vector):
        base_vector = vector[:self.size]
        base_hessian, _ = _fisher_system(self.base, base_vector, self.base.last)
        _, _, jacobian = self.base.predict(base_vector, with_jacobian=True)
        weights = self.likelihood.last_result["row_association_probability"] / 200.**2
        hessian = np.zeros((len(vector), len(vector)))
        hessian[:self.size, :self.size] = base_hessian
        for column in range(self.features.shape[1]):
            physical = jacobian.transpose_multiply(
                (weights * self.features[:, column, None]).ravel())
            cross = self.base.vector_gradient(physical, base_vector)
            hessian[:self.size, self.size + column] = cross
            hessian[self.size + column, :self.size] = cross
        hessian[self.size:, self.size:] = self.features.T @ (
            weights.sum(axis=1)[:, None] * self.features)
        return hessian


def fit_calibrated(data, initial, satellites, separate, *, budget_s=60.):
    if not 0 < budget_s <= 60:
        raise ValueError("calibration fit budget must be in (0,60]")
    objective = CalibrationObjective(data, initial, satellites, separate, budget_s)
    current = objective.initial
    value, gradient = objective.evaluate(current)
    initial_value = value
    trace = []
    damping = 1e-6
    status = "iteration_limit"
    for iteration in range(400):
        try:
            objective.base.check_deadline()
            projected, free = _scaled_projected_gradient(
                current, gradient, objective.bounds, objective.scale)
            norm = float(np.max(np.abs(projected)))
            trace.append({"iteration": iteration, "objective": value,
                          "gradient_norm": norm, "elapsed_s": time.monotonic() - objective.started,
                          "position_km": current[:2].copy(),
                          "rf_coefficient_hz_per_ghz": current[objective.size:].copy()})
            if norm <= 1e-3:
                status = "projected_gradient_converged"
                break
            hessian = objective.curvature(current)
            scaled = objective.scale[:, None] * hessian * objective.scale[None, :]
            scale = max(1., float(np.max(np.diag(scaled))))
            accepted = False
            for _attempt in range(7):
                direction = np.zeros_like(current)
                direction[free] = np.linalg.solve(
                    scaled[np.ix_(free, free)] + damping * scale * np.eye(np.sum(free)),
                    -projected[free])
                direction *= objective.scale
                for fraction in 2. ** -np.arange(12):
                    trial = _project_bounds(current + fraction * direction, objective.bounds)
                    derivative = float(gradient @ (trial - current))
                    if derivative >= 0 or not objective.base.state(
                            trial[:objective.size])["ephemeris_valid"]:
                        continue
                    candidate_value, candidate_gradient = objective.evaluate(trial)
                    if candidate_value <= value + 1e-4 * derivative:
                        current, value, gradient = trial, candidate_value, candidate_gradient
                        accepted = True
                        break
                if accepted:
                    damping = max(1e-12, damping / 10)
                    break
                damping *= 10
            if not accepted:
                status = "no_descent_step"
                break
        except DeadlineReached:
            status = "time_limit"
            break
    if objective.best["objective"] < value - 1e-8:
        current = objective.best["vector"]
    objective.base.deadline = float("inf")
    value, gradient = objective.evaluate(current)
    projected, _ = _scaled_projected_gradient(current, gradient, objective.bounds, objective.scale)
    norm = float(np.max(np.abs(projected)))
    success = norm <= 1e-3
    if success:
        status = "projected_gradient_converged"
    elif status == "projected_gradient_converged":
        status = "retained_state_not_converged"
    state = objective.base.state(current[:objective.size])
    return {**state, "vector": current[:objective.size], "objective": value,
            "initial_objective": initial_value, "success": bool(success), "status": status,
            "projected_gradient_inf_norm": norm, "rf_center_hz": objective.center,
            "rf_coefficient_hz_per_ghz": current[objective.size:],
            "effective_ppm": current[objective.size:] / 1000.,
            "trace": trace, "calls": objective.base.calls,
            "elapsed_s": time.monotonic() - objective.started,
            "sigma_hz": 200., "budget_s": budget_s,
            "convergence_scope": "Projected analytic gradient; local solution, not global optimum",
            "parameters_added": objective.features.shape[1]}


def run_case(cell):
    session, separate = cell
    label = "per-rx" if separate else "common"
    destination = ROOT / "rf-calibration-diagnostic" / f"{session}-{label}.json"
    if destination.exists():
        raise FileExistsError(destination)
    parent_path = ROOT / "runs-continuation" / session / "medium" / "fit.json"
    parent = json.loads(parent_path.read_text())
    hashes = {**parent["source_hashes"], **snapshot_files([__file__, parent_path])}
    assert_snapshot_unchanged(hashes)
    _, data = load_scan(session)
    satellites = np.asarray(parent["fit"]["satellite_indices"], dtype=int)
    fitted = fit_calibrated(data, parent["fit"]["parameters"], satellites, separate)
    assert_snapshot_unchanged(hashes)
    result = {"schema": "ds13-rf-calibration-diagnostic/v1", "session": session,
              "variant": label, "fit": fitted, "source_hashes": hashes,
              "reference_read_in_fitter": False,
              "parent_objective": parent["fit"]["objective"],
              "scope": "Development diagnostic prompted by channel residuals. Same medium soft "
                       "likelihood, timing priors and observations; adds c*(RF-center)/1GHz, "
                       "with c bounded +/-5000 Hz/GHz. Effective ppm is a parametrization, "
                       "not a measurement identifying a particular hardware clock."}
    destination.parent.mkdir(exist_ok=True)
    with destination.open("x") as stream:
        json.dump(serializable(result), stream, indent=2, allow_nan=False)
    return {"session": session, "variant": label, "status": fitted["status"],
            "objective": fitted["objective"], "ppm": fitted["effective_ppm"].tolist(),
            "elapsed_s": fitted["elapsed_s"]}


if __name__ == "__main__":
    sessions = json.loads((ROOT / "protocol-soft.json").read_text())["sessions"]
    with ProcessPoolExecutor(max_workers=2) as executor:
        for row in executor.map(run_case, [(session, separate) for separate in (False, True)
                                          for session in sessions]):
            print(json.dumps(row), flush=True)
