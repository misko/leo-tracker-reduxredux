"""Plug-in relative-RX calibration followed by tied common-RX localization fits."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from coherent_fit import FixedBankLikelihood
from prediction_plan import SharedPredictionPlan
from profile_seed import _validate_source_provenance
from rough_smoke import load_module, serializable
from rx_difference import pair_receiver_groups
from selection import ROOT
from staged_fit import frozen_row_weights
from track_likelihood import prepare_track_grouped_likelihood

DEFAULT_DIAGNOSTIC = ROOT / "rx-difference-diagnostic.json"
DEFAULT_COHORT_SOURCE = ROOT / "runs" / "rx-difference-cohort-v1"
DEFAULT_RUN_ID = "relative-rx-v1"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_digest(values):
    return hashlib.sha256(np.asarray(values, dtype="<f8").tobytes()).hexdigest()


def circular(value, center=0.0):
    alias_hz = 1 / 4.4e-6
    return (np.asarray(value) - center + alias_hz / 2) % alias_hz - alias_hz / 2


@dataclass(frozen=True)
class RelativeCalibration:
    model: str
    parameters: np.ndarray
    reference_time_s: float | None
    start_time_s: float
    end_time_s: float

    def evaluate(self, times):
        times = np.asarray(times, dtype=float)
        if self.model == "line":
            intercept, slope = self.parameters
            return intercept + slope * (times - self.reference_time_s)
        if self.model != "quadratic":
            raise ValueError(f"unsupported differential model {self.model!r}")
        intercept, slope_start, slope_end = self.parameters
        span = self.end_time_s - self.start_time_s
        fraction = (times - self.start_time_s) / span
        return intercept + span * (
            slope_start * fraction + 0.5 * (slope_end - slope_start) * fraction**2
        )

    @property
    def endpoint_slopes_hz_s(self):
        if self.model == "line":
            return np.repeat(self.parameters[1], 2)
        return self.parameters[1:3].copy()


class CalibratedData:
    """Delegate all physical inputs while substituting corrected measurements."""

    def __init__(self, source, calibration):
        self.source = source
        self.calibration = calibration
        delta = calibration.evaluate(source.times)
        signs = np.where(np.asarray(source.receiver) == 0, 0.5, -0.5)
        self.measured = np.asarray(source.measured, dtype=float) + signs * delta

    def __getattr__(self, name):
        return getattr(self.source, name)


def common_slope_bounds(endpoint_delta_slopes, physical_bound_hz_s=50.0):
    slopes = np.asarray(endpoint_delta_slopes, dtype=float)
    if slopes.shape != (2,) or np.any(~np.isfinite(slopes)):
        raise ValueError("differential endpoint slopes must contain two finite values")
    if not np.isfinite(physical_bound_hz_s) or physical_bound_hz_s <= 0:
        raise ValueError("physical slope bound must be positive and finite")
    lower = -np.inf
    upper = np.inf
    for delta_slope in slopes:
        for sign in (-0.5, 0.5):
            lower = max(lower, -physical_bound_hz_s - sign * delta_slope)
            upper = min(upper, physical_bound_hz_s - sign * delta_slope)
    if lower > upper:
        raise ValueError("differential drift leaves no feasible common RX slope")
    return float(lower), float(upper)


def expand_tied_parameters(reduced):
    reduced = np.asarray(reduced, dtype=float)
    if reduced.ndim != 1 or len(reduced) < 4:
        raise ValueError("reduced parameters must contain position and one common RX line")
    full = np.empty(len(reduced) + 2, dtype=float)
    full[:2] = reduced[:2]
    full[2] = reduced[2]
    full[3] = reduced[3]
    full[4] = reduced[2]
    full[5] = reduced[3]
    full[6:] = reduced[4:]
    return full


def reduce_tied_parameters(full):
    full = np.asarray(full, dtype=float)
    if full.ndim != 1 or len(full) < 6:
        raise ValueError("full parameters have the wrong shape")
    reduced = np.empty(len(full) - 2, dtype=float)
    reduced[:2] = full[:2]
    reduced[2] = 0.5 * (full[2] + full[4])
    reduced[3] = 0.5 * (full[3] + full[5])
    reduced[4:] = full[6:]
    return reduced


def tied_transform(candidate_count):
    transform = np.zeros((6 + candidate_count, 4 + candidate_count))
    transform[0, 0] = 1.0
    transform[1, 1] = 1.0
    transform[2, 2] = 1.0
    transform[4, 2] = 1.0
    transform[3, 3] = 1.0
    transform[5, 3] = 1.0
    transform[6:, 4:] = np.eye(candidate_count)
    return transform


class TiedJacobian:
    def __init__(self, base, candidate_count):
        self.base = base
        self.transform = tied_transform(candidate_count)

    def transpose_multiply(self, weights):
        full_gradient = self.base.transpose_multiply(weights)
        return self.transform.T @ full_gradient

    def normal_matrix(self, weights):
        full = self.base.normal_matrix(weights)
        return self.transform.T @ full @ self.transform


class TiedPredictionPlan:
    def __init__(self, data, satellites):
        self.base = SharedPredictionPlan(data, satellites)
        self.candidate_count = len(data.numbers)

    def predict(self, reduced):
        predicted, visible, jacobian = self.base.predict(expand_tied_parameters(reduced))
        return predicted, visible, TiedJacobian(jacobian, self.candidate_count)


def select_differential_calibration(case, paired_times):
    paired_times = np.asarray(paired_times, dtype=float)
    if paired_times.ndim != 1 or len(paired_times) == 0 or np.any(~np.isfinite(paired_times)):
        raise ValueError("paired receive times must be a nonempty finite vector")
    pair_count = int(case["pairing"]["paired_group_count"])
    if pair_count != len(paired_times):
        raise ValueError("reconstructed pair count differs from the sealed diagnostic")
    fit = case["fit"]
    candidates = []
    line = fit["line"]
    candidates.append(
        {
            "model": "line",
            "estimated_parameter_count": 2,
            "objective": float(line["objective"]),
            "parameters": np.asarray([line["intercept_hz_at_reference"], line["slope_hz_s"]]),
            "reference_time_s": float(fit["reference_time_s"]),
        }
    )
    quadratic = fit.get("quadratic")
    if quadratic is not None:
        candidates.append(
            {
                "model": "quadratic",
                "estimated_parameter_count": 3,
                "objective": float(quadratic["objective"]),
                "parameters": np.asarray(
                    [
                        quadratic["intercept_hz_at_start"],
                        quadratic["slope_start_hz_s"],
                        quadratic["slope_end_hz_s"],
                    ]
                ),
                "reference_time_s": None,
            }
        )
    for candidate in candidates:
        candidate["count_penalty"] = (
            0.5 * candidate["estimated_parameter_count"] * np.log(pair_count)
        )
        candidate["penalized_score"] = candidate["objective"] + candidate["count_penalty"]
    calculated = min(candidates, key=lambda candidate: candidate["penalized_score"])
    sealed_model = case.get("selected_model")
    if sealed_model is not None:
        selected = next(
            (candidate for candidate in candidates if candidate["model"] == sealed_model), None
        )
        if selected is None:
            raise ValueError("sealed differential receipt selected an unavailable model")
        if selected["model"] != calculated["model"]:
            raise ValueError("sealed differential model conflicts with the count-penalized score")
        sealed_scores = case.get("penalized_scores")
        if sealed_scores is None or any(
            not np.isclose(
                sealed_scores[candidate["model"]],
                candidate["penalized_score"],
                rtol=0,
                atol=1e-9,
            )
            for candidate in candidates
        ):
            raise ValueError("sealed differential penalized scores do not reproduce")
        selection_source = "sealed cohort receipt selected_model, independently reproduced"
    else:
        selected = calculated
        selection_source = "recomputed from legacy aggregate diagnostic"
    calibration = RelativeCalibration(
        model=selected["model"],
        parameters=selected["parameters"],
        reference_time_s=selected["reference_time_s"],
        start_time_s=float(np.min(paired_times)),
        end_time_s=float(np.max(paired_times)),
    )
    return calibration, {
        "pair_count": pair_count,
        "criterion": "differential objective + 0.5 * parameter_count * log(paired groups)",
        "candidates": candidates,
        "selected_model": selected["model"],
        "selected_by_penalized_score": True,
        "selection_source": selection_source,
        "diagnostic_minimum_objective_field_ignored": True,
    }


def localization_selection_score(objective, satellite_count, group_count, calibration_model):
    if satellite_count <= 0 or group_count <= 0:
        raise ValueError("satellite and group counts must be positive")
    if calibration_model not in ("line", "quadratic"):
        raise ValueError("unknown calibration model")
    satellite_penalty = 0.5 * satellite_count * np.log(group_count)
    extra_parameters = 0 if calibration_model == "line" else 1
    calibration_penalty = 0.5 * extra_parameters * np.log(group_count)
    return {
        "selection_score": float(objective + satellite_penalty + calibration_penalty),
        "satellite_entry_penalty": float(satellite_penalty),
        "calibration_effective_parameter_delta_vs_rx4": extra_parameters,
        "calibration_count_penalty": float(calibration_penalty),
        "differential_likelihood_added_to_localization_objective": False,
    }


class _BudgetExpired(Exception):
    pass


def refine_tied_rx(
    data,
    source_parameters,
    satellites,
    likelihood,
    common_slope_bound,
    *,
    sigma_hz=200.0,
    tau_sigma_s=1.0,
    tau_bound_s=3.0,
    budget_s=15.0,
):
    from scipy.optimize import minimize

    source_parameters = np.asarray(source_parameters, dtype=float)
    satellites = np.asarray(satellites, dtype=int)
    candidate_count = len(data.numbers)
    if source_parameters.shape != (6 + candidate_count,):
        raise ValueError("source parameters do not match the candidate bank")
    if np.any(~np.isfinite(source_parameters)):
        raise ValueError("source parameters must be finite")
    if satellites.ndim != 1 or len(satellites) == 0:
        raise ValueError("satellites must be a nonempty vector")
    if len(np.unique(satellites)) != len(satellites):
        raise ValueError("satellites must be unique")
    if not np.isfinite(budget_s) or not 0 < budget_s <= 15:
        raise ValueError("per-bank budget must lie in (0, 15]")
    lower_slope, upper_slope = common_slope_bound
    reduced_initial = reduce_tied_parameters(source_parameters)
    if not lower_slope <= reduced_initial[3] <= upper_slope:
        raise ValueError("source mean RX slope lies outside the physical intersection")
    active = np.r_[np.arange(4), 4 + satellites]
    scales = np.r_[20.0, 20.0, 1000.0, 10.0, np.ones(len(satellites))]
    bounds = [
        (-10.0, 10.0),
        (-10.0, 10.0),
        (None, None),
        (lower_slope / 10.0, upper_slope / 10.0),
    ] + [(-tau_bound_s, tau_bound_s)] * len(satellites)
    plan = TiedPredictionPlan(data, satellites)
    started = time.monotonic()
    deadline = started + budget_s
    best = None
    evaluations = 0

    def evaluate(vector):
        nonlocal best, evaluations
        if time.monotonic() > deadline:
            raise _BudgetExpired
        reduced = reduced_initial.copy()
        reduced[active] = np.asarray(vector) * scales
        predicted, visible, jacobian = plan.predict(reduced)
        predicted = predicted.reshape(len(data.times), len(satellites))
        visible = visible.reshape(predicted.shape)
        result = likelihood.evaluate(
            predicted,
            visible,
            sigma_hz=sigma_hz,
            satellite_weights=np.ones(len(satellites)) / len(satellites),
            background_mass=0.2,
            return_gradient=True,
            return_precision=False,
        )
        physical_gradient = -jacobian.transpose_multiply(
            np.asarray(result["prediction_gradient"]).ravel()
        )
        tau_indices = 4 + satellites
        tau = reduced[tau_indices]
        prior = 0.5 * np.sum((tau / tau_sigma_s) ** 2)
        physical_gradient[tau_indices] += tau / tau_sigma_s**2
        objective = float(-result["total_log_likelihood"] + prior)
        gradient = physical_gradient[active] * scales
        evaluations += 1
        state = {
            "vector": np.asarray(vector).copy(),
            "reduced": reduced,
            "objective": objective,
            "gradient": gradient,
            "likelihood": {
                key: value for key, value in result.items() if key != "prediction_gradient"
            },
        }
        if best is None or objective < best["objective"]:
            best = state
        return objective, gradient

    vector = reduced_initial[active] / scales
    initial_objective, _ = evaluate(vector)
    optimizer = None
    timed_out = False
    try:
        optimizer = minimize(
            evaluate,
            vector,
            method="L-BFGS-B",
            jac=True,
            bounds=bounds,
            options={"maxiter": 200, "ftol": 1e-12, "gtol": 1e-7, "maxls": 20},
        )
    except _BudgetExpired:
        timed_out = True
    full = expand_tied_parameters(best["reduced"])
    group_count = len(best["likelihood"]["group_values"])
    success = bool(optimizer is not None and optimizer.success and not timed_out)
    return {
        "parameters": full,
        "reduced_parameters": best["reduced"],
        "satellite_indices": satellites,
        "catalog_numbers": np.asarray(data.numbers)[satellites],
        "satellite_count": len(satellites),
        "objective": best["objective"],
        "initial_objective": initial_objective,
        "success": success,
        "status": "converged" if success else "nonconverged",
        "message": "budget_exhausted"
        if timed_out
        else str(optimizer.message if optimizer is not None else "optimizer_not_started"),
        "evaluations": evaluations,
        "elapsed_s": time.monotonic() - started,
        "groups": group_count,
        "sigma_hz": float(sigma_hz),
        "tau_sigma_s": float(tau_sigma_s),
        "tau_bound_s": float(tau_bound_s),
        "common_slope_bounds_hz_s": [float(lower_slope), float(upper_slope)],
        "rx_tie_exact": bool(full[2] == full[4] and full[3] == full[5]),
        "analytic_vjp": "tied gradients sum a0+a1 and b0+b1",
        "satellite_support": best["likelihood"]["satellite_support"],
        "null_support": best["likelihood"]["null_support"],
    }


def _select_trials(trials):
    finite = [trial for trial in trials if np.isfinite(trial["selection_score"])]
    if not finite:
        raise RuntimeError("no relative-RX trial has a finite selection score")
    leader = min(finite, key=lambda trial: (trial["selection_score"], trial["satellite_count"]))
    converged = [trial for trial in finite if trial["success"]]
    converged_leader = (
        None
        if not converged
        else min(
            converged,
            key=lambda trial: (trial["selection_score"], trial["satellite_count"]),
        )
    )
    return {
        "winner": leader,
        "score_leader": leader,
        "converged_leader": converged_leader,
        "selection_resolved": bool(leader["success"]),
        "success": bool(leader["success"]),
    }


def fit_relative_banks(data, expanded, diagnostic_case, *, budget_s_per_bank=15.0):
    expanded_fit = expanded["fit"]
    raw_row_weights = frozen_row_weights(data)
    paired = pair_receiver_groups(data)
    calibration, calibration_selection = select_differential_calibration(
        diagnostic_case, paired.times
    )
    slope_bounds = common_slope_bounds(calibration.endpoint_slopes_hz_s)
    calibrated = CalibratedData(data, calibration)
    anchors = [np.asarray(anchor["groups"]) for anchor in expanded_fit["anchors"]]
    prepared = prepare_track_grouped_likelihood(
        calibrated.measured,
        calibrated.group,
        row_weights=raw_row_weights,
        anchors=anchors,
    )
    trials = []
    for source_trial in expanded_fit["trials"]:
        satellites = np.asarray(source_trial["satellite_indices"], dtype=int)
        source_parameters = np.asarray(source_trial["parameters"], dtype=float)
        likelihood = FixedBankLikelihood(prepared, source_trial["identity_masses"])
        trial = refine_tied_rx(
            calibrated,
            source_parameters,
            satellites,
            likelihood,
            slope_bounds,
            sigma_hz=200.0,
            tau_sigma_s=1.0,
            tau_bound_s=3.0,
            budget_s=budget_s_per_bank,
        )
        score = localization_selection_score(
            trial["objective"],
            len(satellites),
            trial["groups"],
            calibration.model,
        )
        trial.update(score)
        trial["source_parameters"] = source_parameters
        trial["source_parameters_sha256"] = array_digest(source_parameters)
        trial["identity_masses"] = source_trial["identity_masses"]
        trial["likelihood_diagnostics"] = {
            key: value
            for key, value in likelihood.last_result.items()
            if "track" in key or key.endswith("group_count")
        }
        trials.append(trial)
    selected = _select_trials(trials)
    return {
        "trials": trials,
        **selected,
        "full_bank": expanded_fit["full_bank"],
        "anchors": expanded_fit["anchors"],
        "calibration": {
            "model": calibration.model,
            "parameters": calibration.parameters,
            "reference_time_s": calibration.reference_time_s,
            "start_time_s": calibration.start_time_s,
            "end_time_s": calibration.end_time_s,
            "endpoint_slopes_hz_s": calibration.endpoint_slopes_hz_s,
            "common_slope_bounds_hz_s": slope_bounds,
            "measurement_correction": "RX0 += delta(t)/2; RX1 -= delta(t)/2",
        },
        "calibration_selection": calibration_selection,
        "row_weights_frozen_before_measurement_correction": True,
        "differential_likelihood_added_to_localization_objective": False,
        "plug_in_calibration_uncertainty_propagated": False,
        "scope": (
            "The sealed empirical RX1-RX0 curve is a fixed plug-in calibration. Corrected GLRT "
            "groups are evaluated exactly once under the expanded-bank frozen anchors and identity "
            "masses. Only position, one common RX intercept, one common RX slope, and the same "
            "global candidate taus are fitted. Calibration uncertainty is ignored."
        ),
    }


def _load_differential_case(unit_id, source_path):
    source_path = Path(source_path)
    if source_path.is_dir():
        fit_path = source_path / unit_id / "fit.json"
        summary_path = source_path / "summary.json"
        receipt = json.loads(fit_path.read_text())
        summary = json.loads(summary_path.read_text())
        if receipt.get("schema") != "rx-difference-cohort/v1":
            raise ValueError("unsupported differential cohort receipt schema")
        if receipt["unit"]["unit_id"] != unit_id:
            raise ValueError("differential cohort receipt unit mismatch")
        if receipt.get("reference_read") is not False or receipt.get("ephemeris_read") is not False:
            raise ValueError("differential cohort receipt used a forbidden input")
        if summary.get("reference_read") is not False:
            raise ValueError("differential cohort summary lacks truth-free provenance")
        summary_unit = next((row for row in summary["units"] if row["unit_id"] == unit_id), None)
        if summary_unit is None or summary_unit["fit_sha256"] != digest(fit_path):
            raise ValueError("differential cohort summary does not bind the unit receipt")
        if summary_unit["selected_model"] != receipt["selected_model"]:
            raise ValueError("differential cohort summary selected model mismatch")
        if (
            summary["selection_sha256"] != receipt["selection_sha256"]
            or summary["source_sha256"] != receipt["source_sha256"]
        ):
            raise ValueError("differential cohort summary provenance mismatch")
        case = {
            **receipt,
            "unit_id": unit_id,
            "session_id": receipt["unit"]["session_ids"][0],
        }
        return case, {
            "kind": "cohort_unit_receipt",
            "source_path": fit_path,
            "source_sha256": digest(fit_path),
            "summary_path": summary_path,
            "summary_sha256": digest(summary_path),
        }
    diagnostic = json.loads(source_path.read_text())
    if diagnostic.get("schema") != "cross-rx-differential-frequency/v1":
        raise ValueError("unsupported differential diagnostic schema")
    case = next((case for case in diagnostic["cases"] if case["unit_id"] == unit_id), None)
    if case is None:
        raise ValueError(f"differential diagnostic lacks {unit_id}")
    return case, {
        "kind": "legacy_aggregate_diagnostic",
        "source_path": source_path,
        "source_sha256": digest(source_path),
        "summary_path": None,
        "summary_sha256": None,
    }


def _load_case_sources(unit_id, differential_source):
    diagnostic_case, calibration_source = _load_differential_case(unit_id, differential_source)
    expanded_path = ROOT / "runs" / "expanded-bank-v1" / unit_id / "fit.json"
    dense_path = ROOT / "runs" / "dense-anchor-v1" / unit_id / "fit.json"
    expanded = json.loads(expanded_path.read_text())
    dense = json.loads(dense_path.read_text())
    if expanded.get("stage") != "expanded_bank" or expanded["unit"]["unit_id"] != unit_id:
        raise ValueError("expanded source is not the requested frozen unit")
    if expanded.get("reference_read_before_seal") is not False:
        raise ValueError("expanded source lacks truth-free sealing")
    if dense.get("stage") != "dense_anchor" or dense.get("reference_read_before_seal") is not False:
        raise ValueError("dense source lacks standard truth-free provenance")
    if expanded["source_fit_sha256"] != digest(dense_path):
        raise ValueError("expanded source is not bound to the dense source")
    source_validation = _validate_source_provenance(dense)
    if diagnostic_case["session_id"] != expanded["unit"]["session_ids"][0]:
        raise ValueError("diagnostic and expanded source sessions differ")
    if calibration_source["kind"] == "cohort_unit_receipt":
        session_id = diagnostic_case["session_id"]
        bundle_directory = ROOT / "scans" / session_id
        if diagnostic_case["source_sha256"] != digest(ROOT / "rx_difference.py"):
            raise ValueError("differential cohort numerical source digest mismatch")
        if diagnostic_case["selection_sha256"] != source_validation["selection_sha256"]:
            raise ValueError("differential cohort selection digest mismatch")
        if diagnostic_case["bundle_manifest_sha256"] != digest(bundle_directory / "bundle.json"):
            raise ValueError("differential cohort bundle manifest digest mismatch")
        if diagnostic_case["bundle_npz_sha256"] != digest(bundle_directory / "bundle.npz"):
            raise ValueError("differential cohort bundle payload digest mismatch")
    return {
        "diagnostic_case": diagnostic_case,
        "calibration_source": calibration_source,
        "expanded": expanded,
        "expanded_path": expanded_path,
        "expanded_sha256": digest(expanded_path),
        "dense_path": dense_path,
        "dense_sha256": digest(dense_path),
        "source_validation": source_validation,
    }


def run_case(unit_id, run_id, differential_source=DEFAULT_COHORT_SOURCE, budget_s_per_bank=15.0):
    sources = _load_case_sources(unit_id, differential_source)
    expanded = sources["expanded"]
    output = ROOT / "runs" / run_id / unit_id
    output.mkdir(parents=True, exist_ok=False)
    bundle = load_module(
        f"relative_rx_bundle_{unit_id}",
        ROOT.parent / "2026_10_02_localization_benchmark" / "bundle.py",
    )
    session_id = expanded["unit"]["session_ids"][0]
    data = bundle.Data(ROOT / "scans" / session_id)
    started = time.monotonic()
    fitted = fit_relative_banks(
        data,
        expanded,
        sources["diagnostic_case"],
        budget_s_per_bank=budget_s_per_bank,
    )
    receipt = {
        "schema": "relative-rx-localization-fit/v1",
        "stage": "relative_rx",
        "unit": expanded["unit"],
        "dataset": sources["diagnostic_case"]["dataset"],
        "run_id": run_id,
        "rx_calibration_source_kind": sources["calibration_source"]["kind"],
        "rx_calibration_source": str(sources["calibration_source"]["source_path"]),
        "rx_calibration_source_sha256": sources["calibration_source"]["source_sha256"],
        "rx_calibration_summary": None
        if sources["calibration_source"]["summary_path"] is None
        else str(sources["calibration_source"]["summary_path"]),
        "rx_calibration_summary_sha256": sources["calibration_source"]["summary_sha256"],
        "expanded_fit": str(sources["expanded_path"]),
        "expanded_fit_sha256": sources["expanded_sha256"],
        "dense_fit": str(sources["dense_path"]),
        "dense_fit_sha256": sources["dense_sha256"],
        "expanded_source_fit_sha256": expanded["source_fit_sha256"],
        "source_validation": sources["source_validation"],
        "source_hashes": {
            path.name: digest(path)
            for path in sorted(ROOT.glob("*.py"))
            if not path.name.startswith("test_")
        },
        "configuration": {
            "sigma_hz": 200.0,
            "tau_sigma_s": 1.0,
            "tau_bound_s": 3.0,
            "physical_rx_slope_bound_hz_s": 50.0,
            "budget_s_per_bank": float(budget_s_per_bank),
            "case_budget_bound_s": 90.0,
            "optimizer": "analytic-vjp L-BFGS-B",
        },
        "reference_read_before_seal": False,
        "initial_comparison_read_by_fit": False,
        "eligible_for_cohort": False,
        "elapsed_s": time.monotonic() - started,
        "fit": fitted,
        "sealed_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "limitations": (
            "Empirical differential calibration is estimated from the same stored observations "
            "and then treated as fixed. Its uncertainty is not propagated. The differential "
            "likelihood is not added to the localization objective, avoiding a second use as an "
            "independent likelihood term."
        ),
    }
    fit_path = output / "fit.json"
    fit_path.write_text(json.dumps(serializable(receipt), indent=2) + "\n")
    return fit_path, receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    parser.add_argument("--rx-source", type=Path, default=DEFAULT_COHORT_SOURCE)
    parser.add_argument("--rx-diagnostic", type=Path, default=None)
    parser.add_argument("--budget-s-per-bank", type=float, default=15.0)
    args = parser.parse_args()
    if not args.run_id or Path(args.run_id).name != args.run_id or args.run_id in (".", ".."):
        parser.error("run-id must be one path component")
    if not 0 < args.budget_s_per_bank <= 15:
        parser.error("budget-s-per-bank must lie in (0, 15]")
    outputs = []
    differential_source = args.rx_diagnostic or args.rx_source
    for unit_id in ("DS10-S01", "DS11-S02"):
        fit_path, receipt = run_case(
            unit_id,
            args.run_id,
            differential_source=differential_source,
            budget_s_per_bank=args.budget_s_per_bank,
        )
        outputs.append(
            {
                "unit_id": unit_id,
                "fit": str(fit_path),
                "fit_sha256": digest(fit_path),
                "elapsed_s": receipt["elapsed_s"],
                "calibration_model": receipt["fit"]["calibration"]["model"],
                "score_leader_k": receipt["fit"]["score_leader"]["satellite_count"],
                "selection_resolved": receipt["fit"]["selection_resolved"],
            }
        )
    print(json.dumps({"run_id": args.run_id, "outputs": outputs}))


if __name__ == "__main__":
    main()


__all__ = [
    "CalibratedData",
    "RelativeCalibration",
    "TiedJacobian",
    "common_slope_bounds",
    "expand_tied_parameters",
    "fit_relative_banks",
    "localization_selection_score",
    "reduce_tied_parameters",
    "refine_tied_rx",
    "select_differential_calibration",
    "tied_transform",
]
