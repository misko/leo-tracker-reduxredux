"""Pure reception-model evaluation for the roof direction subset.

This module deliberately knows nothing about storage or how rows were derived.
Directions are truth-conditioned diagnostics, not geographic claims.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Mapping, Sequence

import numpy as np


REQUIRED = {
    "session_id", "split", "track_id", "receiver_id", "channel", "edge",
    "anchor_margin", "matched", "log_margin_ratio_rx1_rx0", "east", "up",
}


@dataclass(frozen=True)
class FittedModel:
    outcome: str
    direction: bool
    feature_names: tuple[str, ...]
    channel_levels: tuple[str, ...]
    edge_levels: tuple[str, ...]
    channel_edge_levels: tuple[str, ...]
    sample_rate_levels: tuple[str, ...]
    numeric_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]


def validate_rows(rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError("at least one row is required")
    for row in rows:
        missing = REQUIRED - row.keys()
        if missing:
            raise ValueError(f"row lacks fields: {sorted(missing)}")
        if row["split"] not in {"cal", "holdout"}:
            raise ValueError("split must be 'cal' or 'holdout'")
        if row["receiver_id"] not in {"rx0", "rx1"}:
            raise ValueError("receiver_id must be rx0 or rx1")
        if float(row["anchor_margin"]) <= 0:
            raise ValueError("anchor_margin must be positive")
        if not isinstance(row["matched"], (bool, np.bool_)):
            raise ValueError("matched must be boolean")
        for name in ("east", "up"):
            if not math.isfinite(float(row[name])):
                raise ValueError(f"{name} must be finite")
        ratio = row["log_margin_ratio_rx1_rx0"]
        if ratio is not None and not math.isfinite(float(ratio)):
            raise ValueError("log margin ratio must be finite or null")
        if row.get("sample_rate_hz") is not None and float(row["sample_rate_hz"]) <= 0:
            raise ValueError("sample_rate_hz must be positive when present")


def _track_weights(rows: Sequence[Mapping[str, object]]) -> np.ndarray:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["session_id"]), str(row["track_id"]))
        counts[key] = counts.get(key, 0) + 1
    return np.asarray([
        1.0 / counts[(str(row["session_id"]), str(row["track_id"]))]
        for row in rows
    ])


def track_weights(rows: Sequence[Mapping[str, object]]) -> list[float]:
    """Return weights whose sum is one within each scan/track cluster."""
    return _track_weights(rows).tolist()


def _numeric(row: Mapping[str, object], outcome: str, direction: bool) -> list[float]:
    values: list[float] = []
    if outcome == "detection":
        values.append(math.log(float(row["anchor_margin"])))
    if direction:
        east = float(row["east"])
        if outcome == "detection" and row["receiver_id"] == "rx1":
            east = -east
        values.append(east)
    return values


def _design(
    rows: Sequence[Mapping[str, object]], outcome: str, direction: bool,
    *, template: FittedModel | None = None,
) -> tuple[np.ndarray, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[float, ...], tuple[float, ...], tuple[str, ...]]:
    channels = (template.channel_levels if template else
                tuple(sorted({str(r["channel"]) for r in rows})))
    edges = (template.edge_levels if template else
             tuple(sorted({str(r["edge"]) for r in rows})))
    channel_edges = (template.channel_edge_levels if template else tuple(sorted({
        f'{r["channel"]}:{r["edge"]}' for r in rows
    })))
    rates = (template.sample_rate_levels if template else tuple(sorted({
        str(r.get("sample_rate_hz", "__constant__")) for r in rows
    })))
    numeric_names = (("log_anchor_margin",) if outcome == "detection" else ())
    if direction:
        numeric_names += ("signed_east" if outcome == "detection" else "east",)
    raw = np.asarray([_numeric(r, outcome, direction) for r in rows], dtype=float)
    if raw.shape[1]:
        means = template.means if template else tuple(np.mean(raw, axis=0))
        scales = template.scales if template else tuple(np.std(raw, axis=0))
        scales = tuple(s if s > 1e-12 else 1.0 for s in scales)
        numeric = (raw - np.asarray(means)) / np.asarray(scales)
    else:
        means, scales = (), ()
        numeric = np.empty((len(rows), 0))
    names = ["intercept"]
    columns = [np.ones(len(rows))]
    # A joint lane term prevents direction from proxying channel-specific edge
    # sensitivity.  Separate main effects are intentionally not substituted.
    for level in channel_edges[1:]:
        names.append(f"channel_edge={level}")
        columns.append(np.asarray([
            f'{r["channel"]}:{r["edge"]}' == level for r in rows
        ], float))
    for level in rates[1:]:
        names.append(f"sample_rate_hz={level}")
        columns.append(np.asarray([
            str(r.get("sample_rate_hz", "__constant__")) == level for r in rows
        ], float))
    names.append("receiver=rx1")
    columns.append(np.asarray([r["receiver_id"] == "rx1" for r in rows], float))
    for index, name in enumerate(numeric_names):
        names.append(name)
        columns.append(numeric[:, index])
    return np.column_stack(columns), channels, edges, channel_edges, rates, tuple(numeric_names), tuple(means), tuple(scales), tuple(names)


def _fit(rows: Sequence[Mapping[str, object]], outcome: str, direction: bool, ridge: float) -> FittedModel:
    if ridge < 0:
        raise ValueError("ridge must be nonnegative")
    x, channels, edges, channel_edges, rates, nums, means, scales, names = _design(rows, outcome, direction)
    weights = _track_weights(rows)
    penalty = np.eye(x.shape[1]) * ridge
    penalty[0, 0] = 0.0
    if outcome == "detection":
        y = np.asarray([bool(r["matched"]) for r in rows], float)
        beta = np.zeros(x.shape[1])
        for _ in range(100):
            probability = 1.0 / (1.0 + np.exp(-np.clip(x @ beta, -35, 35)))
            gradient = x.T @ (weights * (probability - y)) + penalty @ beta
            hessian = x.T @ ((weights * probability * (1 - probability))[:, None] * x) + penalty
            step = np.linalg.pinv(hessian) @ gradient
            beta -= step
            if np.max(np.abs(step)) < 1e-10:
                break
    else:
        y = np.asarray([float(r["log_margin_ratio_rx1_rx0"]) for r in rows])
        beta = np.linalg.pinv(x.T @ (weights[:, None] * x) + penalty) @ (x.T @ (weights * y))
    return FittedModel(outcome, direction, names, channels, edges, channel_edges, rates, nums, means, scales, tuple(beta))


def fit_detection_models(rows: Sequence[Mapping[str, object]], ridge: float = 1.0) -> dict[str, FittedModel]:
    validate_rows(rows)
    cal = [r for r in rows if r["split"] == "cal"]
    if not cal:
        raise ValueError("calibration rows are required")
    return {"M0": _fit(cal, "detection", False, ridge), "M1": _fit(cal, "detection", True, ridge)}


def fit_continuous_models(rows: Sequence[Mapping[str, object]], ridge: float = 1.0) -> dict[str, FittedModel]:
    validate_rows(rows)
    cal = [r for r in rows if r["split"] == "cal" and r["log_margin_ratio_rx1_rx0"] is not None]
    if not cal:
        raise ValueError("calibration rows with a log margin ratio are required")
    return {"M0": _fit(cal, "continuous", False, ridge), "M1": _fit(cal, "continuous", True, ridge)}


def predict(model: FittedModel, rows: Sequence[Mapping[str, object]]) -> np.ndarray:
    x, *_ = _design(rows, model.outcome, model.direction, template=model)
    estimate = x @ np.asarray(model.coefficients)
    if model.outcome == "detection":
        return 1.0 / (1.0 + np.exp(-np.clip(estimate, -35, 35)))
    return estimate


def _equal_track_mean(values: np.ndarray, rows: Sequence[Mapping[str, object]]) -> float:
    weights = _track_weights(rows)
    return float(np.sum(weights * values) / np.sum(weights))


def score_models(models: Mapping[str, FittedModel], rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    outcome = models["M0"].outcome
    selected = [r for r in rows if outcome == "detection" or r["log_margin_ratio_rx1_rx0"] is not None]
    if not selected:
        raise ValueError("no scoreable rows")
    losses: dict[str, np.ndarray] = {}
    for name, model in models.items():
        estimate = predict(model, selected)
        if outcome == "detection":
            y = np.asarray([bool(r["matched"]) for r in selected], float)
            losses[name] = -(y * np.log(np.clip(estimate, 1e-12, 1)) +
                             (1 - y) * np.log(np.clip(1 - estimate, 1e-12, 1)))
        else:
            y = np.asarray([float(r["log_margin_ratio_rx1_rx0"]) for r in selected])
            losses[name] = (y - estimate) ** 2
    per_scan = {}
    for scan in sorted({str(r["session_id"]) for r in selected}):
        indices = [i for i, r in enumerate(selected) if str(r["session_id"]) == scan]
        scan_rows = [selected[i] for i in indices]
        per_scan[scan] = {name: _equal_track_mean(loss[np.asarray(indices)], scan_rows) for name, loss in losses.items()}
    overall = {name: _equal_track_mean(loss, selected) for name, loss in losses.items()}
    overall["M1_minus_M0"] = overall["M1"] - overall["M0"]
    known_rates = set(models["M0"].sample_rate_levels)
    unseen_rates = sorted({str(r.get("sample_rate_hz", "__constant__")) for r in selected} - known_rates)
    return {"metric": "log_loss" if outcome == "detection" else "mean_squared_error",
            "equal_track": overall, "per_scan": per_scan,
            "unseen_sample_rate_hz": unseen_rates}


def _shuffle_directions(rows: Sequence[Mapping[str, object]], split: str, seed: int) -> list[dict[str, object]]:
    result = [dict(r) for r in rows]
    rng = np.random.default_rng(seed)
    for session in sorted({str(r["session_id"]) for r in rows if r["split"] == split}):
        keys = sorted({str(r["track_id"]) for r in rows if r["split"] == split and str(r["session_id"]) == session})
        direction = {}
        for key in keys:
            source = [r for r in rows if str(r["session_id"]) == session and str(r["track_id"]) == key]
            source.sort(key=lambda r: int(r.get("observation_utc_ns", 0)))
            direction[key] = [(float(r["east"]), float(r["up"])) for r in source]
        permuted = rng.permutation(keys)
        mapping = dict(zip(keys, permuted, strict=True))
        for key in keys:
            target = [r for r in result if r["split"] == split and str(r["session_id"]) == session and str(r["track_id"]) == key]
            target.sort(key=lambda r: int(r.get("observation_utc_ns", 0)))
            donor = direction[mapping[key]]
            # Transfer the donor direction trajectory, not only its first point.
            indices = np.rint(np.linspace(0, len(donor)-1, len(target))).astype(int)
            for row, index in zip(target, indices, strict=True):
                row["east"], row["up"] = donor[index]
    return result


def permute_calibration_directions(rows: Sequence[Mapping[str, object]], seed: int = 20260927) -> list[dict[str, object]]:
    return _shuffle_directions(rows, "cal", seed)


def shuffle_holdout_directions_within_scan(rows: Sequence[Mapping[str, object]], seed: int = 20260927) -> list[dict[str, object]]:
    return _shuffle_directions(rows, "holdout", seed)


def reverse_mapping(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    result = [dict(r) for r in rows]
    for row in result:
        row["east"] = -float(row["east"])
    return result


def scan_bootstrap(models: Mapping[str, FittedModel], rows: Sequence[Mapping[str, object]], replicates: int = 2000, seed: int = 20260927) -> dict[str, object]:
    if replicates <= 0:
        raise ValueError("replicates must be positive")
    scans = sorted({str(r["session_id"]) for r in rows})
    if not scans:
        raise ValueError("rows are required")
    scored = score_models(models, rows)
    per_scan = scored["per_scan"]
    track_counts = {
        scan: len({str(r["track_id"]) for r in rows if str(r["session_id"]) == scan})
        for scan in scans
    }
    scan_delta = {
        scan: float(per_scan[scan]["M1"] - per_scan[scan]["M0"])
        for scan in scans
    }
    rng = np.random.default_rng(seed)
    deltas = []
    for _ in range(replicates):
        sample = rng.choice(scans, len(scans), replace=True)
        denominator = sum(track_counts[str(scan)] for scan in sample)
        deltas.append(sum(
            track_counts[str(scan)] * scan_delta[str(scan)] for scan in sample
        ) / denominator)
    return {"replicates": replicates, "seed": seed,
            "estimand": "equal_track_loss; scan-cluster bootstrap",
            "M1_minus_M0_95_ci": np.quantile(deltas, [0.025, 0.975]).tolist(),
            "M1_better_fraction": float(np.mean(np.asarray(deltas) < 0))}


def _model_summary(models: Mapping[str, FittedModel]) -> dict[str, object]:
    return {
        name: {
            "features": list(model.feature_names),
            "coefficients": list(model.coefficients),
            "numeric_means": dict(zip(model.numeric_names, model.means, strict=True)),
            "numeric_scales": dict(zip(model.numeric_names, model.scales, strict=True)),
            "channel_levels": list(model.channel_levels),
            "edge_levels": list(model.edge_levels),
            "channel_edge_levels": list(model.channel_edge_levels),
            "sample_rate_levels": list(model.sample_rate_levels),
        }
        for name, model in models.items()
    }


def evaluate(
    rows: Sequence[Mapping[str, object]], ridge: float = 1.0,
    bootstrap_replicates: int = 2000, seed: int = 20260927,
) -> dict[str, object]:
    """Fit on calibration only and evaluate all predeclared held-out diagnostics."""
    validate_rows(rows)
    holdout = [r for r in rows if r["split"] == "holdout"]
    if not holdout:
        raise ValueError("holdout rows are required")
    detection = fit_detection_models(rows, ridge)
    permuted = permute_calibration_directions(rows, seed)
    permutation_models = fit_detection_models(permuted, ridge)
    shuffled_holdout = [r for r in shuffle_holdout_directions_within_scan(rows, seed)
                        if r["split"] == "holdout"]
    known_rates = set(detection["M0"].sample_rate_levels)
    rate_matched_holdout = [
        r for r in holdout
        if str(r.get("sample_rate_hz", "__constant__")) in known_rates
    ]
    excluded_rate_scans = sorted({
        str(r["session_id"]) for r in holdout
        if str(r.get("sample_rate_hz", "__constant__")) not in known_rates
    })
    rate_sensitivity = {
        "rule": "score heldout rows whose sample_rate_hz occurred in calibration; no refit",
        "included_scans": sorted({str(r["session_id"]) for r in rate_matched_holdout}),
        "excluded_scans": excluded_rate_scans,
        "row_count": len(rate_matched_holdout),
        "score": score_models(detection, rate_matched_holdout) if rate_matched_holdout else None,
    }
    output: dict[str, object] = {
        "ridge": ridge,
        "detection": {
            "models": _model_summary(detection),
            "heldout": score_models(detection, holdout),
            "scan_bootstrap": scan_bootstrap(
                detection, holdout, bootstrap_replicates, seed
            ),
            "matched_training_sample_rate_sensitivity": rate_sensitivity,
            "controls": {
                "calibration_direction_permutation": score_models(permutation_models, holdout),
                "heldout_within_scan_track_direction_shuffle": score_models(detection, shuffled_holdout),
                "mapping_reversal": score_models(detection, reverse_mapping(holdout)),
            },
        },
    }
    if any(r["log_margin_ratio_rx1_rx0"] is not None and r["split"] == "cal" for r in rows):
        continuous = fit_continuous_models(rows, ridge)
        continuous_holdout = [r for r in holdout if r["log_margin_ratio_rx1_rx0"] is not None]
        if continuous_holdout:
            permuted_continuous = fit_continuous_models(permuted, ridge)
            output["continuous"] = {
                "models": _model_summary(continuous),
                "heldout": score_models(continuous, continuous_holdout),
                "scan_bootstrap": scan_bootstrap(
                    continuous, continuous_holdout, bootstrap_replicates, seed
                ),
                "matched_training_sample_rate_sensitivity": {
                    **{key: value for key, value in rate_sensitivity.items() if key != "score"},
                    "row_count": len([
                        r for r in rate_matched_holdout
                        if r["log_margin_ratio_rx1_rx0"] is not None
                    ]),
                    "score": score_models(
                        continuous,
                        [r for r in rate_matched_holdout
                         if r["log_margin_ratio_rx1_rx0"] is not None],
                    ) if any(r["log_margin_ratio_rx1_rx0"] is not None
                             for r in rate_matched_holdout) else None,
                },
                "controls": {
                    "calibration_direction_permutation": score_models(
                        permuted_continuous, continuous_holdout
                    ),
                    "heldout_within_scan_track_direction_shuffle": score_models(
                        continuous,
                        [r for r in shuffled_holdout if r["log_margin_ratio_rx1_rx0"] is not None],
                    ),
                    "mapping_reversal": score_models(
                        continuous, reverse_mapping(continuous_holdout)
                    ),
                },
            }
    return output
