"""TLE-free cross-receiver differential-frequency drift diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent
ALIAS_HZ = 1 / 4.4e-6
DEFAULT_SIGMA_HZ = 283.0
DEFAULT_PAIR_TOLERANCE_S = 0.001
DEFAULT_OUTPUT = ROOT / "rx-difference-diagnostic.json"


def circular(value, center=0.0):
    return (np.asarray(value) - center + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


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


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class DifferentialGroups:
    times: np.ndarray
    rf: np.ndarray
    rx0_groups: np.ndarray
    rx1_groups: np.ndarray
    starts: np.ndarray
    counts: np.ndarray
    differences: np.ndarray
    weights: np.ndarray
    metadata: dict

    @property
    def pair_count(self):
        return len(self.times)


def _group_records(data):
    records = []
    for value in np.unique(data.group):
        rows = np.flatnonzero(data.group == value)
        receivers = np.unique(data.receiver[rows])
        frequencies = np.unique(data.rf[rows])
        times = np.asarray(data.times[rows], dtype=float)
        if len(receivers) != 1 or len(frequencies) != 1:
            raise ValueError("each source group must have one RX and RF")
        if np.any(~np.isfinite(times)):
            raise ValueError("source-group receive times must be finite")
        alternatives = np.unique(circular(data.measured[rows]))
        records.append(
            {
                "group": int(value),
                "receiver": int(receivers[0]),
                "rf": float(frequencies[0]),
                "time": float(np.median(times)),
                "time_span_s": float(np.ptp(times)),
                "alternatives": alternatives,
            }
        )
    if any(record["receiver"] not in (0, 1) for record in records):
        raise ValueError("receiver indices must be zero or one")
    return records


def _candidate_edges(left, right, tolerance_s):
    left = sorted(left, key=lambda record: (record["time"], record["group"]))
    right = sorted(right, key=lambda record: (record["time"], record["group"]))
    edges = []
    first = 0
    for record0 in left:
        while first < len(right) and right[first]["time"] < record0["time"] - tolerance_s:
            first += 1
        index = first
        while index < len(right) and right[index]["time"] <= record0["time"] + tolerance_s:
            record1 = right[index]
            edges.append(
                (
                    abs(record1["time"] - record0["time"]),
                    record0["group"],
                    record1["group"],
                    record0,
                    record1,
                )
            )
            index += 1
    return edges


def _aggregate_alternatives(record0, record1):
    alternatives0 = record0["alternatives"]
    alternatives1 = record1["alternatives"]
    differences = circular(alternatives1[:, None] - alternatives0[None, :]).ravel()
    pair_weights = np.full(len(differences), 1.0 / (len(alternatives0) * len(alternatives1)))
    unique, inverse = np.unique(differences, return_inverse=True)
    weights = np.bincount(inverse, weights=pair_weights, minlength=len(unique))
    weights /= weights.sum()
    return unique, weights


def pair_receiver_groups(data, tolerance_s=DEFAULT_PAIR_TOLERANCE_S):
    if not np.isfinite(tolerance_s) or tolerance_s <= 0:
        raise ValueError("pair tolerance must be positive and finite")
    records = _group_records(data)
    frequencies = sorted({record["rf"] for record in records})
    edges = []
    for frequency in frequencies:
        left = [
            record for record in records if record["receiver"] == 0 and record["rf"] == frequency
        ]
        right = [
            record for record in records if record["receiver"] == 1 and record["rf"] == frequency
        ]
        edges.extend(_candidate_edges(left, right, tolerance_s))
    edges.sort(key=lambda edge: (edge[0], edge[1], edge[2]))
    used0 = set()
    used1 = set()
    selected = []
    for edge in edges:
        _, group0, group1, _, _ = edge
        if group0 in used0 or group1 in used1:
            continue
        used0.add(group0)
        used1.add(group1)
        selected.append(edge)
    selected.sort(key=lambda edge: (0.5 * (edge[3]["time"] + edge[4]["time"]), edge[1]))
    if not selected:
        raise ValueError("no cross-RX source groups pair within the fixed tolerance")

    times = []
    rf = []
    groups0 = []
    groups1 = []
    differences = []
    weights = []
    counts = []
    deltas = []
    source_alternatives0 = []
    source_alternatives1 = []
    for delta, group0, group1, record0, record1 in selected:
        values, masses = _aggregate_alternatives(record0, record1)
        times.append(0.5 * (record0["time"] + record1["time"]))
        rf.append(record0["rf"])
        groups0.append(group0)
        groups1.append(group1)
        differences.extend(values)
        weights.extend(masses)
        counts.append(len(values))
        deltas.append(delta)
        source_alternatives0.append(len(record0["alternatives"]))
        source_alternatives1.append(len(record1["alternatives"]))
    counts = np.asarray(counts, dtype=int)
    starts = np.r_[0, np.cumsum(counts[:-1])]
    receiver_counts = {
        receiver: sum(record["receiver"] == receiver for record in records) for receiver in (0, 1)
    }
    deltas = np.asarray(deltas)
    source_group_time_spans = np.asarray([record["time_span_s"] for record in records])
    metadata = {
        "pairing_policy": (
            "Each source group's receive time is its row-time median. Same exact RF; "
            "deterministic globally nearest available RX0/RX1 source groups within 1 ms. "
            "Each source group is used at most once."
        ),
        "pair_tolerance_s": float(tolerance_s),
        "threshold_changed_after_coverage_review": False,
        "source_group_count_rx0": int(receiver_counts[0]),
        "source_group_count_rx1": int(receiver_counts[1]),
        "paired_group_count": len(selected),
        "coverage_rx0": len(selected) / receiver_counts[0],
        "coverage_rx1": len(selected) / receiver_counts[1],
        "unpaired_group_count_rx0": receiver_counts[0] - len(selected),
        "unpaired_group_count_rx1": receiver_counts[1] - len(selected),
        "rf_count": len(frequencies),
        "time_delta_ms": {
            "minimum": float(np.min(deltas) * 1000),
            "median": float(np.median(deltas) * 1000),
            "p90": float(np.quantile(deltas, 0.9) * 1000),
            "p99": float(np.quantile(deltas, 0.99) * 1000),
            "maximum": float(np.max(deltas) * 1000),
        },
        "within_source_group_time_span_ms": {
            "median": float(np.median(source_group_time_spans) * 1000),
            "p90": float(np.quantile(source_group_time_spans, 0.9) * 1000),
            "p99": float(np.quantile(source_group_time_spans, 0.99) * 1000),
            "maximum": float(np.max(source_group_time_spans) * 1000),
        },
        "unique_source_alternatives": {
            "rx0_median": float(np.median(source_alternatives0)),
            "rx0_maximum": int(np.max(source_alternatives0)),
            "rx1_median": float(np.median(source_alternatives1)),
            "rx1_maximum": int(np.max(source_alternatives1)),
        },
        "difference_alternatives": {
            "median": float(np.median(counts)),
            "p90": float(np.quantile(counts, 0.9)),
            "maximum": int(np.max(counts)),
        },
        "evidence_accounting": (
            "One likelihood term per paired source-group pair. Unique alternatives within each "
            "RX group have equal candidate-independent mass; Cartesian RX1-RX0 differences are "
            "categorical alternatives within that one term, never independent observations."
        ),
    }
    return DifferentialGroups(
        times=np.asarray(times),
        rf=np.asarray(rf),
        rx0_groups=np.asarray(groups0, dtype=int),
        rx1_groups=np.asarray(groups1, dtype=int),
        starts=starts,
        counts=counts,
        differences=np.asarray(differences),
        weights=np.asarray(weights),
        metadata=metadata,
    )


class DifferentialLikelihood:
    def __init__(self, groups, sigma_hz=DEFAULT_SIGMA_HZ, signal_mass=0.8):
        if not np.isfinite(sigma_hz) or sigma_hz <= 0:
            raise ValueError("sigma_hz must be positive and finite")
        if not np.isfinite(signal_mass) or not 0 < signal_mass < 1:
            raise ValueError("signal_mass must lie strictly between zero and one")
        self.groups = groups
        self.sigma_hz = float(sigma_hz)
        self.signal_mass = float(signal_mass)
        self.owners = np.repeat(np.arange(groups.pair_count), groups.counts)

    def evaluate(self, model, design=None):
        model = np.asarray(model, dtype=float)
        if model.shape != (self.groups.pair_count,):
            raise ValueError("model must have one value per paired group")
        residual = circular(self.groups.differences, model[self.owners])
        shifts = residual[:, None] + ALIAS_HZ * np.arange(-2, 3)[None, :]
        normalizer = self.sigma_hz * np.sqrt(2 * np.pi)
        component = np.exp(-0.5 * (shifts / self.sigma_hz) ** 2) / normalizer
        density = np.sum(component, axis=1)
        density_derivative = np.sum(component * shifts / self.sigma_hz**2, axis=1)
        group_signal = np.add.reduceat(self.groups.weights * density, self.groups.starts)
        group_derivative = np.add.reduceat(
            self.groups.weights * density_derivative, self.groups.starts
        )
        mixture = self.signal_mass * group_signal + (1 - self.signal_mass) / ALIAS_HZ
        objective = -float(np.sum(np.log(mixture)))
        result = {
            "objective": objective,
            "group_log_likelihood": np.log(mixture),
            "group_signal_responsibility": self.signal_mass * group_signal / mixture,
        }
        if design is not None:
            design = np.asarray(design, dtype=float)
            if design.shape[0] != self.groups.pair_count:
                raise ValueError("design must align with paired groups")
            model_score = self.signal_mass * group_derivative / mixture
            result["gradient"] = -(design.T @ model_score)
        return result


def _line_design(times, reference_time):
    return np.column_stack([np.ones(len(times)), times - reference_time])


def _quadratic_design(times, start_time, end_time):
    span = end_time - start_time
    if span <= 0:
        raise ValueError("quadratic fit requires a positive time span")
    fraction = (times - start_time) / span
    return np.column_stack(
        [
            np.ones(len(times)),
            span * (fraction - 0.5 * fraction**2),
            0.5 * span * fraction**2,
        ]
    )


def coarse_hough(groups, likelihood, reference_time, *, slope_step_hz_s=5.0, bins=512):
    if slope_step_hz_s != 5.0:
        raise ValueError("the diagnostic contract fixes the Hough slope step at 5 Hz/s")
    slopes = np.arange(-100.0, 100.0 + slope_step_hz_s / 2, slope_step_hz_s)
    centers = np.linspace(-ALIAS_HZ / 2, ALIAS_HZ / 2, bins, endpoint=False) + ALIAS_HZ / (2 * bins)
    expanded_time = np.repeat(groups.times - reference_time, groups.counts)
    candidates = []
    for slope in slopes:
        intercepts = circular(groups.differences - slope * expanded_time)
        histogram, _ = np.histogram(
            intercepts,
            bins=bins,
            range=(-ALIAS_HZ / 2, ALIAS_HZ / 2),
            weights=groups.weights,
        )
        for index in np.argsort(-histogram, kind="stable")[:3]:
            parameters = np.array([centers[index], slope])
            model = _line_design(groups.times, reference_time) @ parameters
            objective = likelihood.evaluate(model)["objective"]
            candidates.append(
                {
                    "intercept_hz": float(parameters[0]),
                    "slope_hz_s": float(parameters[1]),
                    "histogram_mass": float(histogram[index]),
                    "objective": objective,
                }
            )
    candidates.sort(key=lambda row: (row["objective"], -row["histogram_mass"], row["slope_hz_s"]))
    seeds = []
    for candidate in candidates:
        key = (candidate["intercept_hz"], candidate["slope_hz_s"])
        if key not in {(seed["intercept_hz"], seed["slope_hz_s"]) for seed in seeds}:
            seeds.append(candidate)
        if len(seeds) == 3:
            break
    return seeds


def _project(vector, bounds):
    result = np.asarray(vector, dtype=float).copy()
    for index, (lower, upper) in enumerate(bounds):
        result[index] = min(max(result[index], lower), upper)
    return result


def _optimize(design, likelihood, initial, bounds, scales, deadline):
    scales = np.asarray(scales, dtype=float)
    scaled_bounds = [
        (lower / scale, upper / scale) for (lower, upper), scale in zip(bounds, scales, strict=True)
    ]
    vector = _project(np.asarray(initial) / scales, scaled_bounds)
    inverse_hessian = np.eye(len(vector))
    evaluations = 0

    def evaluate(candidate):
        nonlocal evaluations
        if time.monotonic() > deadline:
            raise TimeoutError
        parameters = candidate * scales
        result = likelihood.evaluate(design @ parameters, design)
        evaluations += 1
        return result["objective"], result["gradient"] * scales

    objective, gradient = evaluate(vector)
    best = (objective, vector.copy(), gradient.copy())
    accepted_steps = 0
    status = "iteration_limit"
    try:
        for _ in range(150):
            if np.max(np.abs(gradient)) <= 1e-5:
                status = "gradient"
                break
            direction = -(inverse_hessian @ gradient)
            maximum = np.max(np.abs(direction))
            if maximum > 1:
                direction /= maximum
            accepted = None
            for fraction in (1.0, 0.5, 0.25, 0.125, 0.0625, 0.03125):
                candidate = _project(vector + fraction * direction, scaled_bounds)
                if np.array_equal(candidate, vector):
                    continue
                candidate_objective, candidate_gradient = evaluate(candidate)
                if candidate_objective < objective:
                    accepted = candidate, candidate_objective, candidate_gradient
                    break
            if accepted is None:
                inverse_hessian = np.eye(len(vector))
                direction = -gradient / max(1.0, np.max(np.abs(gradient)))
                candidate = _project(vector + 0.01 * direction, scaled_bounds)
                candidate_objective, candidate_gradient = evaluate(candidate)
                if candidate_objective >= objective:
                    status = "no_decrease"
                    break
                accepted = candidate, candidate_objective, candidate_gradient
            candidate, candidate_objective, candidate_gradient = accepted
            step = candidate - vector
            change = candidate_gradient - gradient
            curvature = float(step @ change)
            if curvature > 1e-12:
                identity = np.eye(len(vector))
                outer = np.outer(step, change) / curvature
                inverse_hessian = (identity - outer) @ inverse_hessian @ (
                    identity - outer.T
                ) + np.outer(step, step) / curvature
            else:
                inverse_hessian = np.eye(len(vector))
            vector = candidate
            objective = candidate_objective
            gradient = candidate_gradient
            accepted_steps += 1
            if objective < best[0]:
                best = (objective, vector.copy(), gradient.copy())
            if np.max(np.abs(step)) <= 1e-8:
                status = "step"
                break
    except TimeoutError:
        status = "budget_exhausted"
    return {
        "parameters": best[1] * scales,
        "objective": float(best[0]),
        "gradient_inf_norm_scaled": float(np.max(np.abs(best[2]))),
        "evaluations": evaluations,
        "accepted_steps": accepted_steps,
        "status": status,
    }


def fit_difference_models(
    groups,
    *,
    sigma_hz=DEFAULT_SIGMA_HZ,
    signal_mass=0.8,
    include_quadratic=True,
    budget_s=30.0,
):
    if not np.isfinite(budget_s) or not 0 < budget_s <= 30:
        raise ValueError("case fit budget must be in (0, 30] seconds")
    started = time.monotonic()
    deadline = started + budget_s
    reference_time = 0.5 * (float(np.min(groups.times)) + float(np.max(groups.times)))
    likelihood = DifferentialLikelihood(groups, sigma_hz=sigma_hz, signal_mass=signal_mass)
    seeds = coarse_hough(groups, likelihood, reference_time)
    line_design = _line_design(groups.times, reference_time)
    line_trials = []
    for seed in seeds:
        initial = [seed["intercept_hz"], seed["slope_hz_s"]]
        line_trials.append(
            _optimize(
                line_design,
                likelihood,
                initial,
                [(-ALIAS_HZ / 2, ALIAS_HZ / 2), (-100.0, 100.0)],
                [1000.0, 10.0],
                deadline,
            )
        )
    line = min(line_trials, key=lambda trial: trial["objective"])
    line["intercept_hz_at_reference"] = float(circular(line["parameters"][0]))
    line["slope_hz_s"] = float(line["parameters"][1])
    line["parameters"] = np.array([line["intercept_hz_at_reference"], line["slope_hz_s"]])

    quadratic = None
    quadratic_trials = []
    if include_quadratic:
        start_time = float(np.min(groups.times))
        end_time = float(np.max(groups.times))
        quadratic_design = _quadratic_design(groups.times, start_time, end_time)
        for seed in seeds:
            initial = [seed["intercept_hz"], seed["slope_hz_s"], seed["slope_hz_s"]]
            quadratic_trials.append(
                _optimize(
                    quadratic_design,
                    likelihood,
                    initial,
                    [
                        (-ALIAS_HZ / 2, ALIAS_HZ / 2),
                        (-100.0, 100.0),
                        (-100.0, 100.0),
                    ],
                    [1000.0, 10.0, 10.0],
                    deadline,
                )
            )
        quadratic = min(quadratic_trials, key=lambda trial: trial["objective"])
        intercept, slope_start, slope_end = quadratic["parameters"]
        span = end_time - start_time
        quadratic.update(
            {
                "intercept_hz_at_start": float(circular(intercept)),
                "slope_start_hz_s": float(slope_start),
                "slope_end_hz_s": float(slope_end),
                "total_change_hz": float(0.5 * span * (slope_start + slope_end)),
                "endpoint_slope_bound_hz_s": 100.0,
            }
        )
        quadratic["parameters"] = np.array(
            [quadratic["intercept_hz_at_start"], slope_start, slope_end]
        )
    selected = min(
        [("line", line), *(([("quadratic", quadratic)]) if quadratic is not None else [])],
        key=lambda item: item[1]["objective"],
    )
    return {
        "reference_time_s": reference_time,
        "sigma_hz": float(sigma_hz),
        "signal_mass": float(signal_mass),
        "uniform_null_mass": float(1 - signal_mass),
        "hough": {
            "slope_min_hz_s": -100.0,
            "slope_max_hz_s": 100.0,
            "slope_step_hz_s": 5.0,
            "intercept_bins": 512,
            "seeds": seeds,
        },
        "line": line,
        "line_trials": line_trials,
        "quadratic": quadratic,
        "quadratic_trials": quadratic_trials,
        "minimum_objective_model": selected[0],
        "elapsed_s": time.monotonic() - started,
        "budget_s": float(budget_s),
        "scope": (
            "Cross-RX RX1-RX0 differential frequency only. No TLE, position, source fit, or "
            "reference coordinates enter pairing, Hough seeding, likelihood, or optimization. "
            "Common-mode receiver drift and position effects are not identifiable here."
        ),
    }


def postseal_model_comparison(fit, initial):
    initial = np.asarray(initial, dtype=float)
    if initial.ndim != 1 or len(initial) < 6 or np.any(~np.isfinite(initial[:6])):
        raise ValueError("post-seal model RX parameters are invalid")
    model_intercept_150 = float(initial[4] - initial[2])
    model_slope = float(initial[5] - initial[3])
    reference_time = fit["reference_time_s"]
    model_intercept = model_intercept_150 + model_slope * (reference_time - 150.0)
    line = fit["line"]
    return {
        "performed_after_fit_sealed": True,
        "used_by_fitter": False,
        "model_rx1_minus_rx0_intercept_hz_at_reference": float(circular(model_intercept)),
        "model_rx1_minus_rx0_slope_hz_s": model_slope,
        "fitted_minus_model_intercept_hz": float(
            circular(line["intercept_hz_at_reference"], model_intercept)
        ),
        "fitted_minus_model_slope_hz_s": line["slope_hz_s"] - model_slope,
    }


def _load_layout(directory):
    directory = Path(directory)
    manifest_path = directory / "bundle.json"
    archive_path = directory / "bundle.npz"
    manifest = json.loads(manifest_path.read_text())
    expected = manifest.get("artifacts", {}).get("bundle_npz_sha256")
    if expected and digest(archive_path) != expected:
        raise ValueError("bundle archive digest does not match its manifest")
    with np.load(archive_path, allow_pickle=False) as arrays:
        layout = SimpleNamespace(
            **{
                name: arrays[name].copy()
                for name in ("times", "measured", "rf", "receiver", "group")
            }
        )
    return layout, manifest, archive_path, manifest_path


def run_unit(unit, dataset, *, include_quadratic=True, budget_s=30.0):
    session_id = unit["session_ids"][0]
    directory = ROOT / "scans" / session_id
    layout, manifest, archive_path, manifest_path = _load_layout(directory)
    started = time.monotonic()
    groups = pair_receiver_groups(layout, tolerance_s=DEFAULT_PAIR_TOLERANCE_S)
    fit = fit_difference_models(
        groups,
        include_quadratic=include_quadratic,
        budget_s=budget_s,
    )
    with np.load(archive_path, allow_pickle=False) as arrays:
        comparison = postseal_model_comparison(fit, arrays["initial"].copy())
    return {
        "unit_id": unit["unit_id"],
        "dataset": dataset,
        "session_id": session_id,
        "bundle_manifest_sha256": digest(manifest_path),
        "bundle_npz_sha256": digest(archive_path),
        "bundle_dataset": manifest["dataset"],
        "pairing": groups.metadata,
        "fit": fit,
        "postseal_model_comparison": comparison,
        "elapsed_s": time.monotonic() - started,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, default=ROOT / "selection.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--budget-s", type=float, default=30.0)
    parser.add_argument("--no-quadratic", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    selection = json.loads(args.selection.read_text())
    requested = (("DS10", "DS10-S01"), ("DS11", "DS11-S02"))
    cases = []
    for dataset, unit_id in requested:
        units = selection["datasets"][dataset]["units"]
        unit = next(unit for unit in units if unit["unit_id"] == unit_id)
        cases.append(
            run_unit(
                unit,
                dataset,
                include_quadratic=not args.no_quadratic,
                budget_s=args.budget_s,
            )
        )
    report = {
        "schema": "cross-rx-differential-frequency/v1",
        "selection_sha256": digest(args.selection),
        "pair_tolerance_s": DEFAULT_PAIR_TOLERANCE_S,
        "threshold_changed_after_coverage_review": False,
        "cases": cases,
        "limitations": (
            "This TLE-free diagnostic can recover only relative RX1-RX0 drift. It cannot identify "
            "common-mode LNB drift, observer position, satellite identity, or absolute Doppler."
        ),
        "fitting_inputs_excluded": [
            "TLE and ephemeris states",
            "position",
            "source-fit parameters",
            "reference coordinates",
            "post-seal model RX parameters",
        ],
    }
    args.output.write_text(json.dumps(jsonable(report), indent=2) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "cases": [
                    {
                        "unit_id": case["unit_id"],
                        "pairs": case["pairing"]["paired_group_count"],
                        "line_slope_hz_s": case["fit"]["line"]["slope_hz_s"],
                        "quadratic_slopes_hz_s": None
                        if case["fit"]["quadratic"] is None
                        else [
                            case["fit"]["quadratic"]["slope_start_hz_s"],
                            case["fit"]["quadratic"]["slope_end_hz_s"],
                        ],
                        "elapsed_s": case["elapsed_s"],
                    }
                    for case in cases
                ],
            }
        )
    )


if __name__ == "__main__":
    main()


__all__ = [
    "ALIAS_HZ",
    "DEFAULT_PAIR_TOLERANCE_S",
    "DEFAULT_SIGMA_HZ",
    "DifferentialGroups",
    "DifferentialLikelihood",
    "circular",
    "coarse_hough",
    "fit_difference_models",
    "pair_receiver_groups",
    "postseal_model_comparison",
]
