"""Apply a frozen receiver-geometry model to a compatible new dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_geometry_fit import DIMENSIONS, evaluate, raw_features, signal_arrays

CONTROLS = ("swap", "reverse")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _session_ids(document: dict) -> set[str]:
    return {lane["lane"]["session_id"] for lane in document.get("lanes", [])}


def validate_frozen_model(model: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Validate and return the immutable scaler and clutter intensities."""
    if model.get("schema") != "rx-geometry-association-pilot/v1":
        raise ValueError("unsupported frozen model schema")
    if model.get("status") != "complete":
        raise ValueError("frozen model is not complete")
    sigma = float(model.get("sigma_hz", math.nan))
    if not np.isfinite(sigma) or not 100.0 <= sigma <= 20_000.0:
        raise ValueError("frozen sigma is outside the declared pilot bounds")
    lambdas = np.asarray(model.get("clutter_intensities"), dtype=float)
    if lambdas.shape != (2,) or not np.all(np.isfinite(lambdas)):
        raise ValueError("frozen clutter intensities must contain two finite values")
    if np.any(lambdas < math.exp(-5.0)) or np.any(lambdas > math.exp(4.0)):
        raise ValueError("frozen clutter intensities are outside fit bounds")
    center = np.asarray(model.get("feature_center"), dtype=float)
    scale = np.asarray(model.get("feature_scale"), dtype=float)
    if center.shape != (8,) or scale.shape != (8,):
        raise ValueError("frozen feature scaler must have eight entries")
    if not np.all(np.isfinite(center)) or not np.all(np.isfinite(scale)) or np.any(scale <= 0):
        raise ValueError("frozen feature scaler must be finite with positive scales")
    fits = model.get("fits", {})
    for arm, dimension in DIMENSIONS.items():
        fitted = fits.get(arm, {})
        parameters = np.asarray(fitted.get("parameters"), dtype=float)
        if fitted.get("success") is not True or parameters.shape != (dimension,):
            raise ValueError(f"frozen {arm} fit is absent, unsuccessful, or malformed")
        if not np.all(np.isfinite(parameters)):
            raise ValueError(f"frozen {arm} coefficients must be finite")
    return center, scale, lambdas


def prepare_target(document: dict, center: np.ndarray, scale: np.ndarray) -> list[dict]:
    """Construct scoring arrays using the saved scaler, without calibration."""
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported target dataset schema")
    lanes = []
    for source in document.get("lanes", []):
        if not source.get("windows"):
            continue
        if source.get("recording_split") != "evaluation":
            raise ValueError("target lanes must be marked evaluation")
        features, visible, mu = raw_features(source)
        roles = np.asarray([window["role"] for window in source["windows"]])
        if not {"reception", "held_frequency"} <= set(roles):
            raise ValueError("each target lane must contain reception and held-frequency windows")
        counts = np.asarray(
            [
                [len(window["observed"][receiver]) for receiver in ("rx0", "rx1")]
                for window in source["windows"]
            ],
            dtype=int,
        )
        prior = np.asarray(
            [
                component["log_prior"] if component["log_prior"] is not None else -np.inf
                for component in source["components"]
            ],
            dtype=float,
        )
        if not np.any(np.isfinite(prior)):
            raise ValueError("target lane has no component with finite prior mass")
        lanes.append(
            {
                "source": source,
                "x": (features - center) / scale,
                "visible": visible,
                "mu": mu,
                "roles": roles,
                "counts": counts,
                "prior": prior,
            }
        )
    if not lanes:
        raise ValueError("target dataset has no scoreable lanes")
    return lanes


def build_report(
    model: dict,
    target: dict,
    training: dict,
    *,
    model_bytes: bytes,
    target_bytes: bytes,
    training_bytes: bytes,
    allow_overlap: bool = False,
) -> dict:
    """Apply a validated frozen model without fitting or scaler recomputation."""
    center, scale, lambdas = validate_frozen_model(model)
    if training.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported training dataset schema")
    training_digest = _sha256(training_bytes)
    if model.get("dataset_sha256") != training_digest:
        raise ValueError("training dataset does not match the frozen model binding")
    training_sessions = _session_ids(training)
    target_sessions = _session_ids(target)
    overlap = sorted(training_sessions & target_sessions)
    if overlap and not allow_overlap:
        raise ValueError("target sessions overlap the frozen pilot dataset")

    lanes = prepare_target(target, center, scale)
    signal_arrays(lanes, float(model["sigma_hz"]))
    evaluations = {}
    for arm in DIMENSIONS:
        beta = np.asarray(model["fits"][arm]["parameters"], dtype=float)
        evaluations[arm] = evaluate(lanes, beta, lambdas, center, scale)
    beta_t = np.asarray(model["fits"]["T"]["parameters"], dtype=float)
    for control in CONTROLS:
        evaluations[control] = evaluate(lanes, beta_t, lambdas, center, scale, control)

    denominators = [
        {sid: row["held_windows"] for sid, row in evaluation["recordings"].items()}
        for evaluation in evaluations.values()
    ]
    if any(denominator != denominators[0] for denominator in denominators[1:]):
        raise ValueError("arm/control evaluation denominators differ")
    contrasts = {}
    for left, right in (
        ("T", "D"),
        ("S", "D"),
        ("T", "S"),
        ("T", "swap"),
        ("T", "reverse"),
    ):
        contrasts[f"{left}-{right}"] = {
            sid: evaluations[left]["recordings"][sid]["log_score_per_window"]
            - evaluations[right]["recordings"][sid]["log_score_per_window"]
            for sid in evaluations[left]["recordings"]
        }
    return {
        "schema": "rx-geometry-frozen-score/v1",
        "status": "complete",
        "source_sha256": {
            "model": _sha256(model_bytes),
            "training_dataset": training_digest,
            "target_dataset": _sha256(target_bytes),
        },
        "model_dataset_sha256": model["dataset_sha256"],
        "training_session_count": len(training_sessions),
        "target_session_count": len(target_sessions),
        "overlapping_sessions": overlap,
        "descriptive_overlap_replay": bool(overlap),
        "evaluations": evaluations,
        "contrasts_per_record": contrasts,
        "contrasts_equal_record_mean": {
            name: float(np.mean(list(values.values()))) for name, values in contrasts.items()
        },
        "interpretation": "Frozen model application with no refit or target-scaler recomputation.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--training-dataset", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--allow-overlap",
        action="store_true",
        help="allow a descriptive replay on sessions used by the original pilot",
    )
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payloads = {
        "model": args.model.read_bytes(),
        "training": args.training_dataset.read_bytes(),
        "target": args.dataset.read_bytes(),
    }
    report = build_report(
        json.loads(payloads["model"]),
        json.loads(payloads["target"]),
        json.loads(payloads["training"]),
        model_bytes=payloads["model"],
        target_bytes=payloads["target"],
        training_bytes=payloads["training"],
        allow_overlap=args.allow_overlap,
    )
    with args.output.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
