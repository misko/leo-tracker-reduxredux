"""In-sample paired-RX score-to-width diagnostic with frozen drift curves."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rx_difference

ROOT = Path(__file__).resolve().parent
DEFAULT_RUN_ROOT = ROOT / "runs" / "rx-difference-cohort-v1"
DEFAULT_OUTPUT = ROOT / "paired-rx-width-diagnostic.json"
SIGMA_MIN_HZ = 100.0
SIGMA_MAX_HZ = 3000.0
SIGNAL_MASS = 0.8


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


@dataclass(frozen=True)
class ScoredDifferenceGroups:
    unit_id: str
    dataset: str
    times: np.ndarray
    starts: np.ndarray
    counts: np.ndarray
    differences: np.ndarray
    weights: np.ndarray
    margins: np.ndarray
    model: np.ndarray
    pairing: dict

    @property
    def pair_count(self) -> int:
        return len(self.times)


def _unique_alternatives(measured: np.ndarray, margin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = rx_difference.circular(np.asarray(measured, dtype=float))
    margins = np.asarray(margin, dtype=float)
    if values.shape != margins.shape or np.any(~np.isfinite(margins)):
        raise ValueError("candidate frequencies and margins must be aligned and finite")
    unique, inverse = np.unique(values, return_inverse=True)
    scores = np.full(len(unique), -np.inf)
    np.maximum.at(scores, inverse, margins)
    return unique, scores


def _scored_groups(layout, paired, unit_id: str, dataset: str, model: np.ndarray):
    differences = []
    margins = []
    weights = []
    counts = []
    for group0, group1 in zip(paired.rx0_groups, paired.rx1_groups, strict=True):
        rows0 = np.flatnonzero(layout.group == group0)
        rows1 = np.flatnonzero(layout.group == group1)
        values0, margins0 = _unique_alternatives(
            layout.measured[rows0], layout.margin[rows0]
        )
        values1, margins1 = _unique_alternatives(
            layout.measured[rows1], layout.margin[rows1]
        )
        current = rx_difference.circular(values1[:, None] - values0[None, :]).ravel()
        current_margins = np.minimum(margins1[:, None], margins0[None, :]).ravel()
        count = len(current)
        differences.extend(current)
        margins.extend(current_margins)
        weights.extend(np.full(count, 1.0 / count))
        counts.append(count)
    counts = np.asarray(counts, dtype=int)
    starts = np.r_[0, np.cumsum(counts[:-1])]
    result = ScoredDifferenceGroups(
        unit_id=unit_id,
        dataset=dataset,
        times=paired.times.copy(),
        starts=starts,
        counts=counts,
        differences=np.asarray(differences),
        weights=np.asarray(weights),
        margins=np.asarray(margins),
        model=np.asarray(model, dtype=float),
        pairing=paired.metadata,
    )
    if result.model.shape != result.times.shape:
        raise ValueError("frozen drift model must provide one mean per paired group")
    group_mass = np.add.reduceat(result.weights, result.starts)
    if np.any(~np.isfinite(result.margins)) or not np.allclose(group_mass, 1.0):
        raise ValueError("categorical alternatives must have finite scores and unit group mass")
    return result


def frozen_model(groups, fit_receipt: dict) -> np.ndarray:
    fit = fit_receipt["fit"]
    selected = fit_receipt["selected_model"]
    if selected == "line":
        row = fit["line"]
        parameters = np.asarray(row["parameters"], dtype=float)
        design = rx_difference._line_design(groups.times, float(fit["reference_time_s"]))
    elif selected == "quadratic":
        row = fit["quadratic"]
        parameters = np.asarray(row["parameters"], dtype=float)
        design = rx_difference._quadratic_design(
            groups.times, float(np.min(groups.times)), float(np.max(groups.times))
        )
    else:
        raise ValueError("frozen RX-difference receipt selected an unknown model")
    if np.any(~np.isfinite(parameters)):
        raise ValueError("frozen drift parameters must be finite")
    return design @ parameters


def score_fraction(margins, score_min, score_max):
    if score_max <= score_min:
        return np.zeros_like(np.asarray(margins, dtype=float))
    return (np.asarray(margins, dtype=float) - score_min) / (score_max - score_min)


def sigma_from_endpoints(margins, endpoint_log_sigma, score_min, score_max):
    low_score_log_sigma, high_score_log_sigma = np.asarray(endpoint_log_sigma, dtype=float)
    fraction = score_fraction(margins, score_min, score_max)
    log_sigma = (1.0 - fraction) * low_score_log_sigma + fraction * high_score_log_sigma
    return np.exp(
        np.clip(log_sigma, math.log(SIGMA_MIN_HZ), math.log(SIGMA_MAX_HZ))
    )


def _case_nll(case: ScoredDifferenceGroups, sigma_hz) -> tuple[float, np.ndarray]:
    sigma = np.broadcast_to(np.asarray(sigma_hz, dtype=float), case.differences.shape)
    if np.any(~np.isfinite(sigma)) or np.any(sigma < SIGMA_MIN_HZ) or np.any(
        sigma > SIGMA_MAX_HZ
    ):
        raise ValueError("all widths must remain within the frozen diagnostic bounds")
    owners = np.repeat(np.arange(case.pair_count), case.counts)
    residual = rx_difference.circular(case.differences, case.model[owners])
    shifts = residual[:, None] + rx_difference.ALIAS_HZ * np.arange(-2, 3)[None, :]
    component = np.exp(-0.5 * (shifts / sigma[:, None]) ** 2) / (
        sigma[:, None] * np.sqrt(2 * np.pi)
    )
    density = np.sum(component, axis=1)
    group_signal = np.add.reduceat(case.weights * density, case.starts)
    mixture = SIGNAL_MASS * group_signal + (1 - SIGNAL_MASS) / rx_difference.ALIAS_HZ
    group_nll = -np.log(mixture)
    return float(np.sum(group_nll)), group_nll


def _case_nll_log_sigma_gradient(case, log_sigma, design):
    log_sigma = np.asarray(log_sigma, dtype=float)
    design = np.asarray(design, dtype=float)
    if log_sigma.shape != case.differences.shape or design.shape[0] != len(log_sigma):
        raise ValueError("log-width gradient inputs must align with difference alternatives")
    log_min = math.log(SIGMA_MIN_HZ)
    log_max = math.log(SIGMA_MAX_HZ)
    tolerance = 16 * np.finfo(float).eps
    if np.any(log_sigma < log_min - tolerance) or np.any(log_sigma > log_max + tolerance):
        raise ValueError("gradient widths must remain within the diagnostic bounds")
    sigma = np.exp(np.clip(log_sigma, log_min, log_max))
    owners = np.repeat(np.arange(case.pair_count), case.counts)
    residual = rx_difference.circular(case.differences, case.model[owners])
    shifts = residual[:, None] + rx_difference.ALIAS_HZ * np.arange(-2, 3)[None, :]
    scaled = shifts / sigma[:, None]
    component = np.exp(-0.5 * scaled**2) / (sigma[:, None] * np.sqrt(2 * np.pi))
    density = np.sum(component, axis=1)
    density_log_sigma_derivative = np.sum(component * (scaled**2 - 1.0), axis=1)
    group_signal = np.add.reduceat(case.weights * density, case.starts)
    weighted_derivative = (
        case.weights[:, None] * density_log_sigma_derivative[:, None] * design
    )
    group_derivative = np.add.reduceat(weighted_derivative, case.starts, axis=0)
    mixture = SIGNAL_MASS * group_signal + (1 - SIGNAL_MASS) / rx_difference.ALIAS_HZ
    group_nll = -np.log(mixture)
    gradient = -np.sum(SIGNAL_MASS * group_derivative / mixture[:, None], axis=0)
    return float(np.sum(group_nll)), gradient


def total_nll(cases, mode: str, parameters, score_min: float, score_max: float):
    total = 0.0
    for case in cases:
        if mode == "constant":
            sigma = float(np.exp(np.asarray(parameters, dtype=float)[0]))
        elif mode == "monotone":
            sigma = sigma_from_endpoints(case.margins, parameters, score_min, score_max)
        else:
            raise ValueError("unknown width model")
        total += _case_nll(case, sigma)[0]
    return total


def total_nll_gradient(cases, mode: str, parameters, score_min: float, score_max: float):
    parameters = np.asarray(parameters, dtype=float)
    total = 0.0
    gradient = np.zeros_like(parameters)
    for case in cases:
        if mode == "constant":
            design = np.ones((len(case.differences), 1))
            log_sigma = np.full(len(case.differences), parameters[0])
        elif mode == "monotone":
            fraction = score_fraction(case.margins, score_min, score_max)
            design = np.column_stack([1.0 - fraction, fraction])
            log_sigma = design @ parameters
        else:
            raise ValueError("unknown width model")
        objective, current_gradient = _case_nll_log_sigma_gradient(
            case, log_sigma, design
        )
        total += objective
        gradient += current_gradient
    return total, gradient


def fit_width_models(cases, deadline: float):
    from scipy.optimize import Bounds, LinearConstraint, minimize

    if not cases:
        raise ValueError("at least one successful paired-RX case is required")
    score_min = min(float(np.min(case.margins)) for case in cases)
    score_max = max(float(np.max(case.margins)) for case in cases)
    pair_count = sum(case.pair_count for case in cases)
    evaluations = {"learned_constant": 0, "monotone": 0}

    fixed_nll = total_nll(
        cases, "constant", [math.log(rx_difference.DEFAULT_SIGMA_HZ)], score_min, score_max
    )

    def constant_objective(log_sigma):
        if time.monotonic() > deadline:
            raise TimeoutError("global width diagnostic budget exhausted")
        evaluations["learned_constant"] += 1
        objective, gradient = total_nll_gradient(
            cases, "constant", log_sigma, score_min, score_max
        )
        return objective / pair_count, gradient / pair_count

    log_min = math.log(SIGMA_MIN_HZ)
    log_max = math.log(SIGMA_MAX_HZ)
    learned = minimize(
        constant_objective,
        np.array([math.log(rx_difference.DEFAULT_SIGMA_HZ)]),
        jac=True,
        bounds=Bounds([log_min], [log_max]),
        method="L-BFGS-B",
        options={"ftol": 1e-12, "maxiter": 100},
    )
    learned_parameters = np.asarray(learned.x, dtype=float)
    learned_nll = total_nll(
        cases, "constant", learned_parameters, score_min, score_max
    )

    def monotone_objective(endpoint_log_sigma):
        if time.monotonic() > deadline:
            raise TimeoutError("global width diagnostic budget exhausted")
        evaluations["monotone"] += 1
        objective, gradient = total_nll_gradient(
            cases, "monotone", endpoint_log_sigma, score_min, score_max
        )
        return objective / pair_count, gradient / pair_count

    monotone = minimize(
        monotone_objective,
        np.repeat(learned_parameters, 2),
        jac=True,
        method="SLSQP",
        bounds=Bounds([log_min, log_min], [log_max, log_max]),
        constraints=(LinearConstraint([[1.0, -1.0]], [0.0], [np.inf]),),
        options={"ftol": 1e-12, "maxiter": 100},
    )
    monotone_parameters = np.asarray(monotone.x, dtype=float)
    monotone_nll = total_nll(
        cases, "monotone", monotone_parameters, score_min, score_max
    )
    log_n = math.log(pair_count)

    def result(name, nll, parameter_count, details):
        return {
            "model": name,
            "negative_log_likelihood": float(nll),
            "parameter_count": parameter_count,
            "conditional_bic_half_penalty": 0.5 * parameter_count * log_n,
            "penalized_negative_log_likelihood": float(
                nll + 0.5 * parameter_count * log_n
            ),
            **details,
        }

    low_log, high_log = monotone_parameters
    beta = (low_log - high_log) / (score_max - score_min) if score_max > score_min else 0.0
    alpha = low_log + beta * score_min
    return {
        "score_range": {"minimum": score_min, "maximum": score_max},
        "pair_count": pair_count,
        "fixed_283_hz": result(
            "constant_sigma_283_hz", fixed_nll, 0, {"sigma_hz": 283.0}
        ),
        "learned_constant": result(
            "learned_constant_sigma",
            learned_nll,
            1,
            {
                "sigma_hz": float(np.exp(learned_parameters[0])),
                "success": bool(learned.success),
                "message": str(learned.message),
                "evaluations": evaluations["learned_constant"],
            },
        ),
        "monotone": result(
            "monotone_log_sigma",
            monotone_nll,
            2,
            {
                "formula": "log(sigma_hz) = alpha - beta * margin",
                "alpha": float(alpha),
                "beta": float(beta),
                "beta_nonnegative": bool(beta >= 0),
                "sigma_hz_at_minimum_score": float(np.exp(low_log)),
                "sigma_hz_at_maximum_score": float(np.exp(high_log)),
                "success": bool(monotone.success),
                "message": str(monotone.message),
                "evaluations": evaluations["monotone"],
            },
        ),
    }


def _case_contributions(case, models, score_min, score_max):
    learned_sigma = models["learned_constant"]["sigma_hz"]
    monotone = models["monotone"]
    parameters = np.array(
        [
            math.log(monotone["sigma_hz_at_minimum_score"]),
            math.log(monotone["sigma_hz_at_maximum_score"]),
        ]
    )
    return {
        "fixed_283_hz_nll": _case_nll(case, 283.0)[0],
        "learned_constant_nll": _case_nll(case, learned_sigma)[0],
        "monotone_nll": _case_nll(
            case, sigma_from_endpoints(case.margins, parameters, score_min, score_max)
        )[0],
    }


def _load_layout(directory: Path):
    manifest_path = directory / "bundle.json"
    archive_path = directory / "bundle.npz"
    manifest = json.loads(manifest_path.read_text())
    with np.load(archive_path, allow_pickle=False) as arrays:
        layout = SimpleNamespace(
            **{
                name: arrays[name].copy()
                for name in ("times", "measured", "rf", "receiver", "group", "margin")
            }
        )
    return layout, manifest, archive_path, manifest_path


def load_case(dataset, unit, run_root: Path):
    unit_id = unit["unit_id"]
    session_id = unit["session_ids"][0]
    fit_path = run_root / unit_id / "fit.json"
    directory = ROOT / "scans" / session_id
    paths = {
        "fit": fit_path,
        "bundle_npz": directory / "bundle.npz",
        "bundle_json": directory / "bundle.json",
    }
    before = {name: digest(path) for name, path in paths.items()}
    fit_receipt = json.loads(fit_path.read_text())
    layout, manifest, archive_path, manifest_path = _load_layout(directory)
    if (
        fit_receipt.get("reference_read") is not False
        or fit_receipt.get("ephemeris_read") is not False
    ):
        raise ValueError("RX-difference receipt is not truth-free")
    if fit_receipt["unit"]["unit_id"] != unit_id or fit_receipt["unit"]["session_ids"] != [
        session_id
    ]:
        raise ValueError("RX-difference receipt unit identity differs")
    if fit_receipt["bundle_npz_sha256"] != before["bundle_npz"] or fit_receipt[
        "bundle_manifest_sha256"
    ] != before["bundle_json"]:
        raise ValueError("RX-difference receipt does not bind the current bundle")
    if fit_receipt["source_sha256"] != digest(Path(rx_difference.__file__).resolve()):
        raise ValueError("RX-difference receipt does not bind the current fitting source")
    if manifest["dataset"] != dataset or manifest["session_id"] != session_id:
        raise ValueError("bundle identity differs from frozen unit")
    paired = rx_difference.pair_receiver_groups(layout)
    model = frozen_model(paired, fit_receipt)
    case = _scored_groups(layout, paired, unit_id, dataset, model)
    after = {name: digest(path) for name, path in paths.items()}
    if before != after:
        raise RuntimeError("case inputs changed during diagnostic loading")
    return case, {
        "unit_id": unit_id,
        "dataset": dataset,
        "session_id": session_id,
        "status": "ready",
        "selected_drift_model": fit_receipt["selected_model"],
        "pair_count": case.pair_count,
        "difference_alternative_count": len(case.differences),
        "score_minimum": float(np.min(case.margins)),
        "score_maximum": float(np.max(case.margins)),
        "input_sha256_pre": before,
        "input_sha256_post": after,
        "inputs_unchanged_during_case": True,
    }


def selected_single_units(selection: dict, requested: set[str] | None = None):
    rows = []
    for dataset in ("DS10", "DS11"):
        for unit in selection["datasets"][dataset]["units"]:
            if unit["size"] == 1 and (requested is None or unit["unit_id"] in requested):
                rows.append((dataset, unit))
    return rows


def run(selection_path: Path, run_root: Path, requested, budget_s: float):
    if not 0 < budget_s <= 90:
        raise ValueError("total diagnostic budget must be in (0, 90] seconds")
    started = time.monotonic()
    deadline = started + budget_s
    source_paths = (Path(__file__).resolve(), Path(rx_difference.__file__).resolve())
    source_before = {str(path): digest(path) for path in source_paths}
    selection = json.loads(selection_path.read_text())
    cases = []
    statuses = []
    for dataset, unit in selected_single_units(selection, requested):
        if time.monotonic() > deadline:
            statuses.append(
                {"unit_id": unit["unit_id"], "dataset": dataset, "status": "budget_exhausted"}
            )
            continue
        try:
            case, status = load_case(dataset, unit, run_root)
            cases.append(case)
            statuses.append(status)
        except Exception as error:
            statuses.append(
                {
                    "unit_id": unit["unit_id"],
                    "dataset": dataset,
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    models = fit_width_models(cases, deadline)
    score_range = models["score_range"]
    by_unit = {row["unit_id"]: row for row in statuses}
    for case in cases:
        by_unit[case.unit_id]["conditional_nll"] = _case_contributions(
            case, models, score_range["minimum"], score_range["maximum"]
        )
        by_unit[case.unit_id]["status"] = "complete"
    source_after = {str(path): digest(path) for path in source_paths}
    if source_before != source_after:
        raise RuntimeError("diagnostic dependencies changed during execution")
    return {
        "schema": "paired-rx-score-width-diagnostic/v1",
        "scope": (
            "In-sample descriptive conditional-width calibration using all requested paired-RX "
            "data. It is not holdout validation or evidence of generalization. Frozen selected "
            "RX1-RX0 drift means are not reoptimized."
        ),
        "selection_sha256": digest(selection_path),
        "source_sha256_pre": source_before,
        "source_sha256_post": source_after,
        "source_unchanged_during_run": True,
        "models": models,
        "cases": statuses,
        "elapsed_s": time.monotonic() - started,
        "budget_s": float(budget_s),
        "limitations": [
            "The result describes combined RX1-RX0 variance, not either receiver individually.",
            (
                "Common-mode drift, source Doppler, observer position, and absolute frequency "
                "error are not identifiable."
            ),
            (
                "Categorical difference alternatives are a conditional approximation whose "
                "physical multiplicity is not validated."
            ),
            (
                "Each paired source-group pair contributes one normalized mixture term; "
                "alternatives are not independent samples."
            ),
            "No calibrated width is promoted into a geolocation fit by this diagnostic.",
        ],
        "excluded_inputs": [
            "TLE or ephemeris states",
            "geolocation fits",
            "reference coordinates",
            "evaluation.json files",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, default=ROOT / "selection.json")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--unit", action="append", dest="units")
    parser.add_argument("--budget-s", type=float, default=90.0)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    requested = None if args.units is None else set(args.units)
    report = run(args.selection, args.run_root, requested, args.budget_s)
    args.output.write_text(json.dumps(jsonable(report), indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "complete": sum(case["status"] == "complete" for case in report["cases"]),
                "failed": sum(case["status"] != "complete" for case in report["cases"]),
                "pairs": report["models"]["pair_count"],
                "fixed_sigma_hz": 283.0,
                "learned_sigma_hz": report["models"]["learned_constant"]["sigma_hz"],
                "monotone_sigma_endpoints_hz": [
                    report["models"]["monotone"]["sigma_hz_at_minimum_score"],
                    report["models"]["monotone"]["sigma_hz_at_maximum_score"],
                ],
                "elapsed_s": report["elapsed_s"],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "ScoredDifferenceGroups",
    "fit_width_models",
    "frozen_model",
    "sigma_from_endpoints",
    "total_nll",
    "total_nll_gradient",
]
