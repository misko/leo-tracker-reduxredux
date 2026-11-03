"""Six-fold calibration comparison of absolute and within-lane geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from tools.rx_background_crossvalidation import calibration_rows
from tools.rx_empirical_background import fit
from tools.rx_geometry_fit import raw_features
from tools.rx_joint_geometry import attach_reference
from tools.rx_joint_geometry_fit import DIMENSIONS, calibration_score, fit_arms

SIGMA_HZ = 500.0
ARMS = tuple(DIMENSIONS)
CHECKPOINT_SCHEMA = "rx-within-geometry-cv-fold/v1"


def reception_document(document):
    """Copy only calibration reception windows needed by this experiment."""
    lanes = []
    for lane in document.get("lanes", []):
        if lane.get("recording_split") != "calibration":
            continue
        windows = [
            window for window in lane.get("windows", []) if window.get("role") == "reception"
        ]
        if windows:
            lanes.append({**lane, "windows": windows})
    return {"schema": document.get("schema"), "lanes": lanes}


def fold_scaler(document, held_session):
    """Compute a scaler from other-record calibration reception forecasts only."""
    reception = reception_document(document)
    blocks = []
    for lane in reception["lanes"]:
        if lane["lane"]["session_id"] == held_session:
            continue
        raw = raw_features(lane)[0][:, :-1]
        blocks.append(raw.reshape(-1, 8))
    if not blocks:
        raise ValueError("empty fold training geometry")
    values = np.concatenate(blocks)
    center, scale = values.mean(axis=0), values.std(axis=0)
    center[0], scale[0] = 0.0, 1.0
    scale[scale < 1e-12] = 1.0
    return center, scale


def prepare_reception_lanes(document, center, scale):
    """Build minimal calibration-reception lanes without reading excluded rows."""
    lanes = []
    for source in reception_document(document)["lanes"]:
        x, visible, mu = raw_features(source)
        times_ns = np.asarray([window["prediction_utc_ns"] for window in source["windows"]])
        if not np.issubdtype(times_ns.dtype, np.integer):
            raise ValueError("prediction times must be integer nanoseconds")
        prior = np.asarray(
            [
                component["log_prior"] if component["log_prior"] is not None else -np.inf
                for component in source["components"][:-1]
            ],
            dtype=float,
        )
        normalizer = float(np.logaddexp.reduce(prior))
        if not np.isfinite(normalizer):
            raise ValueError("lane has no finite nomination prior")
        lanes.append(
            {
                "source": source,
                "x": (x - center) / scale,
                "visible": visible,
                "mu": mu,
                "roles": np.asarray(["reception"] * len(source["windows"])),
                "counts": np.asarray(
                    [
                        [len(window["observed"][receiver]) for receiver in ("rx0", "rx1")]
                        for window in source["windows"]
                    ],
                    dtype=int,
                ),
                "prior": prior - normalizer,
                "times": (times_ns - times_ns[0]) / 1e9,
            }
        )
    return lanes


def within_center(lanes):
    """Return lane copies with columns 3:8 centered over reception time."""
    output = []
    for lane in lanes:
        changed = {**lane, "x": lane["x"].copy()}
        changed["x"][..., 3:8] -= changed["x"][..., 3:8].mean(axis=0, keepdims=True)
        output.append(changed)
    return output


def _json_hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _source_fingerprint():
    directory = Path(__file__).parent
    names = (
        "rx_within_geometry_cv.py",
        "rx_joint_geometry_fit.py",
        "rx_joint_geometry.py",
        "rx_empirical_background.py",
        "rx_empirical_signal.py",
    )
    return {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}


def run(
    document,
    *,
    fold_index=None,
    checkpoint_dir=None,
    dataset_sha256=None,
    experiment_seal=None,
):
    if checkpoint_dir is not None and not experiment_seal:
        raise ValueError("experiment_seal is required with checkpoint_dir")
    if dataset_sha256 is None:
        dataset_sha256 = _json_hash(document)
    rows = calibration_rows(document)
    sessions = sorted({row["session_id"] for row in rows})
    reception = reception_document(document)
    folds = []
    old_fits = {"D": {"parameters": [-2.0, 0.0, 0.0]}}
    settings = {
        "sigma_hz": SIGMA_HZ,
        "arms": list(ARMS),
        "background_mode": "joint",
        "families": ["absolute", "within"],
    }
    fingerprint = {
        "experiment_seal": experiment_seal,
        "settings": settings,
        "source_sha256": _source_fingerprint(),
    }
    for fold_number, held_session in enumerate(sessions, start=1):
        zero_index = fold_number - 1
        checkpoint = None
        if checkpoint_dir is not None:
            checkpoint = checkpoint_dir / f"fold-{zero_index}.json"
            if checkpoint.exists():
                stored = json.loads(checkpoint.read_text())
                expected_training = sorted(set(sessions) - {held_session})
                if (
                    stored.get("schema") != CHECKPOINT_SCHEMA
                    or stored.get("dataset_sha256") != dataset_sha256
                    or stored.get("held_session") != held_session
                    or stored.get("training_sessions") != expected_training
                    or stored.get("fingerprint") != fingerprint
                ):
                    raise ValueError("checkpoint provenance or fold membership mismatch")
                folds.append(stored["fold"])
                continue
        if fold_index is not None and zero_index != fold_index:
            continue
        print(json.dumps({"fold": fold_number, "held_session": held_session}), flush=True)
        training_rows = [row for row in rows if row["session_id"] != held_session]
        held_rows = [row for row in rows if row["session_id"] == held_session]
        background = fit(training_rows, "joint")
        center, scale = fold_scaler(document, held_session)
        prepared = prepare_reception_lanes(reception, center, scale)
        referenced = attach_reference(prepared, background, SIGMA_HZ, calibration_only=True)
        training = [
            lane for lane in referenced if lane["source"]["lane"]["session_id"] != held_session
        ]
        held = [lane for lane in referenced if lane["source"]["lane"]["session_id"] == held_session]
        if not training or not held:
            raise ValueError("fold has empty training or held population")
        families = {}
        for family, family_training, family_held in (
            ("absolute", training, held),
            ("within", within_center(training), within_center(held)),
        ):
            print(
                json.dumps({"fold": fold_number, "family": family, "stage": "fit"}),
                flush=True,
            )
            fit_result = fit_arms(family_training, old_fits)
            window_count = sum(len(lane["times"]) for lane in family_held)
            reference_score = math.fsum(float(lane["reference"].sum()) for lane in family_held)
            scores = {}
            for arm in ARMS:
                selected = fit_result["fits"][arm]["selected"]
                relative = calibration_score(
                    family_held,
                    np.asarray(selected["beta"]),
                    selected["occupancy"],
                    selected["tau_s"],
                )
                scores[arm] = {
                    "relative_log_score": relative,
                    "versus_reference_per_window": relative / window_count,
                    "full_log_score": reference_score + relative,
                    "full_log_score_per_window": (reference_score + relative) / window_count,
                }
            families[family] = {
                "fits": fit_result["fits"],
                "held_windows": window_count,
                "reference_log_score": reference_score,
                "scores": scores,
            }
        if families["absolute"]["fits"]["D"] != families["within"]["fits"]["D"]:
            raise ValueError("absolute and within D fits differ")
        if families["absolute"]["scores"]["D"] != families["within"]["scores"]["D"]:
            raise ValueError("absolute and within D held scores differ")
        training_window_ids = sorted(row["window_id"] for row in training_rows)
        fold = {
            "held_session": held_session,
            "training_sessions": sorted(set(sessions) - {held_session}),
            "feature_center": center.tolist(),
            "feature_scale": scale.tolist(),
            "background_model": background,
            "background_model_sha256": _json_hash(background),
            "held_window_ids": [row["window_id"] for row in held_rows],
            "training_window_count": len(training_window_ids),
            "training_window_ids_sha256": _json_hash(training_window_ids),
            "families": families,
        }
        folds.append(fold)
        if checkpoint is not None:
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            with checkpoint.open("x") as stream:
                json.dump(
                    {
                        "schema": CHECKPOINT_SCHEMA,
                        "dataset_sha256": dataset_sha256,
                        "held_session": held_session,
                        "training_sessions": fold["training_sessions"],
                        "fingerprint": fingerprint,
                        "fold": fold,
                    },
                    stream,
                    indent=2,
                )

    if len(folds) != len(sessions):
        return {
            "schema": "rx-within-geometry-cv/v1",
            "status": "incomplete",
            "sigma_hz": SIGMA_HZ,
            "completed_folds": sorted(fold["held_session"] for fold in folds),
            "folds": folds,
        }
    folds.sort(key=lambda fold: fold["held_session"])

    aggregates = {}
    for family in ("absolute", "within"):
        for arm in ARMS:
            values = {
                fold["held_session"]: fold["families"][family]["scores"][arm][
                    "versus_reference_per_window"
                ]
                for fold in folds
            }
            aggregates[f"{family}_{arm}-reference"] = {
                "records": values,
                "mean": float(np.mean(list(values.values()))),
                "positive_records": sum(value > 0 for value in values.values()),
            }
        for arm in ("E", "S", "T"):
            values = {
                fold["held_session"]: fold["families"][family]["scores"][arm][
                    "versus_reference_per_window"
                ]
                - fold["families"][family]["scores"]["D"]["versus_reference_per_window"]
                for fold in folds
            }
            aggregates[f"{family}_{arm}-{family}_D"] = {
                "records": values,
                "mean": float(np.mean(list(values.values()))),
                "positive_records": sum(value > 0 for value in values.values()),
            }
    for arm in ("E", "S", "T"):
        values = {
            fold["held_session"]: fold["families"]["within"]["scores"][arm][
                "versus_reference_per_window"
            ]
            - fold["families"]["absolute"]["scores"][arm]["versus_reference_per_window"]
            for fold in folds
        }
        aggregates[f"within_{arm}-absolute_{arm}"] = {
            "records": values,
            "mean": float(np.mean(list(values.values()))),
            "positive_records": sum(value > 0 for value in values.values()),
        }
    values = {
        fold["held_session"]: fold["families"]["within"]["scores"]["T"][
            "versus_reference_per_window"
        ]
        - fold["families"]["within"]["scores"]["S"]["versus_reference_per_window"]
        for fold in folds
    }
    aggregates["within_T-within_S"] = {
        "records": values,
        "mean": float(np.mean(list(values.values()))),
        "positive_records": sum(value > 0 for value in values.values()),
    }
    return {
        "schema": "rx-within-geometry-cv/v1",
        "status": "complete",
        "sigma_hz": SIGMA_HZ,
        "folds": folds,
        "aggregates": aggregates,
        "primary": {
            "within_T-minus_D": aggregates["within_T-within_D"],
            "within_T-minus_S": aggregates["within_T-within_S"],
        },
        "interpretation": "Calibration-only descriptive within-geometry cross-validation; "
        "no final refit or evaluation scoring.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path)
    parser.add_argument("--fold-index", type=int, choices=range(6))
    parser.add_argument("--experiment-seal")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if args.checkpoint_dir is not None and not args.experiment_seal:
        parser.error("--experiment-seal is required with --checkpoint-dir")
    payload = args.dataset.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    result = run(
        json.loads(payload),
        fold_index=args.fold_index,
        checkpoint_dir=args.checkpoint_dir,
        dataset_sha256=digest,
        experiment_seal=args.experiment_seal,
    )
    result["dataset_sha256"] = digest
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
