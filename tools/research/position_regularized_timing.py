"""Bounded train/validation diagnostic for a scan-clock shrinkage penalty."""

# ruff: noqa: E402
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"

import matplotlib.pyplot as plt
import numpy as np

REFERENCE = (37.84903264307456, -122.4856541910174)
LAMBDAS = (0.0, 100.0, 1_000.0, 10_000.0, 100_000.0)


def _joint_module():
    path = Path(__file__).with_name("sixteen_joint_compare.py")
    spec = importlib.util.spec_from_file_location("regularized_joint", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, path


def _weight(prediction):
    return int(len(np.unique(np.floor(prediction.times_s).astype(int))))


def _rms(rows):
    denominator = sum(weight for weight, _ in rows)
    return float(np.sqrt(sum(weight * value**2 for weight, value in rows) / denominator))


def profile_track(prediction, tau_index):
    """Profile identity and constant CFO using only the randomized training rows."""
    train = np.asarray(prediction.training_mask, dtype=bool)
    residual = prediction.measured_hz[None, :] - prediction.predictions_hz[:, tau_index, :]
    cfo = residual[:, train].mean(axis=1)
    centered = residual - cfo[:, None]
    train_mse = np.mean(centered[:, train] ** 2, axis=1)
    visible = np.asarray(prediction.visible, dtype=bool)
    train_mse = np.where(visible, train_mse, np.inf)
    candidate = int(np.argmin(train_mse))
    if not np.isfinite(train_mse[candidate]):
        return None
    return {
        "tau_s": float(prediction.taus_s[tau_index]),
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "cfo_hz": float(cfo[candidate]),
        "training_rms_hz": float(np.sqrt(train_mse[candidate])),
        "reserved_rms_hz": float(np.sqrt(np.mean(centered[candidate, ~train] ** 2))),
    }


def scan_choices(profiles, taus_s, penalty, hard_shared=False):
    """Choose a grid clock and per-track tau values from training profiles only.

    The optimization is raw training MSE + penalty*(tau-clock)^2.  Capped RMS is
    solely the aggregate reporting/location metric, so it cannot alter identity,
    CFO, tau, or clock selection.
    """
    n_tau = len(taus_s)
    clock_values = []
    clock_indices = []
    for clock in range(n_tau):
        selected = []
        value = 0.0
        for per_tau in profiles:
            if hard_shared:
                choice = clock
            else:
                values = [
                    (item["training_rms_hz"] ** 2 if item else np.inf)
                    + penalty * (taus_s[index] - taus_s[clock]) ** 2
                    for index, item in enumerate(per_tau)
                ]
                choice = int(np.argmin(values))
            row = per_tau[choice]
            # An unmatched track contributes the same capped failure outcome at
            # every clock.  Exclude that constant from clock profiling so it
            # cannot turn every score into infinity and pin the clock at -5 s.
            if row is not None:
                value += (
                    row["training_rms_hz"] ** 2 + penalty * (taus_s[choice] - taus_s[clock]) ** 2
                )
            selected.append(choice)
        clock_values.append(value)
        clock_indices.append(selected)
    winner = int(np.argmin(clock_values))
    return {
        "clock_tau_s": float(taus_s[winner]),
        "choice_indices": clock_indices[winner],
        "penalized_train_sse_hz2": float(clock_values[winner]),
    }


def score_scan(predictions, penalty, hard_shared=False):
    taus = np.asarray(predictions[0].taus_s, dtype=float)
    profiles = [[profile_track(item, tau) for tau in range(len(taus))] for item in predictions]
    inferred = scan_choices(profiles, taus, penalty, hard_shared)
    choices = [
        per_tau[index] for per_tau, index in zip(profiles, inferred["choice_indices"], strict=True)
    ]
    train = [
        (_weight(prediction), min(800.0, row["training_rms_hz"] if row else 800.0))
        for prediction, row in zip(predictions, choices, strict=True)
    ]
    reserved = [
        (_weight(prediction), min(800.0, row["reserved_rms_hz"] if row else 800.0))
        for prediction, row in zip(predictions, choices, strict=True)
    ]
    return {
        **inferred,
        "training_capped_weighted_rms_hz": _rms(train),
        "reserved_capped_weighted_rms_hz": _rms(reserved),
        "choices": choices,
    }


def score_location(scans, penalty, hard_shared=False):
    answers = [score_scan(predictions, penalty, hard_shared) for _, predictions in scans]
    train, reserved = [], []
    for (_, predictions), answer in zip(scans, answers, strict=True):
        for prediction, choice in zip(predictions, answer["choices"], strict=True):
            train.append(
                (_weight(prediction), min(800.0, choice["training_rms_hz"] if choice else 800.0))
            )
            reserved.append(
                (_weight(prediction), min(800.0, choice["reserved_rms_hz"] if choice else 800.0))
            )
    return {
        "training_capped_weighted_rms_hz": _rms(train),
        "reserved_capped_weighted_rms_hz": _rms(reserved),
        "scan_clock_tau_s": [answer["clock_tau_s"] for answer in answers],
        "penalized_train_sse_hz2": float(
            sum(answer["penalized_train_sse_hz2"] for answer in answers)
        ),
    }


def select_by_reserved(rows):
    return min(rows, key=lambda row: (row["reserved_capped_weighted_rms_hz"], row["label"]))


def select_by_training(rows):
    """Location selection for retrospective windows; never inspect held-out rows."""
    return min(rows, key=lambda row: (row["training_capped_weighted_rms_hz"], row["label"]))


def _cache_index(replication_root):
    index, digests = {}, {}
    for block in sorted(replication_root.glob("block_*")):
        manifest_path = block / "cache/cache_manifest.json"
        if not manifest_path.is_file():
            continue
        raw = manifest_path.read_bytes()
        digests[block.name] = "sha256:" + hashlib.sha256(raw).hexdigest()
        for row in json.loads(raw)["scans"]:
            if row["session_id"] in index:
                raise ValueError(f"duplicate cached session ID: {row['session_id']}")
            index[row["session_id"]] = block / "cache"
    return index, digests


def _validate_points(points):
    if len(points) != 3:
        raise ValueError("exactly three fixed points required")
    ids = [point.get("location_id") for point in points]
    coordinates = [(point.get("latitude_deg"), point.get("longitude_deg")) for point in points]
    if any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("fixed points require nonempty location_id")
    if len(set(ids)) != 3 or len(set(coordinates)) != 3:
        raise ValueError("fixed points require distinct IDs and coordinates")
    if any(not all(isinstance(value, (int, float)) for value in pair) for pair in coordinates):
        raise ValueError("fixed points require numeric latitude_deg and longitude_deg")


def _validate_sealed_inputs(sealed, bindings, models):
    expected = (
        "dataset_manifest_sha256",
        "locations_sha256",
        "cache_manifests",
        "joint_source_sha256",
    )
    stored = sealed.get("bindings", {})
    for key in expected:
        if stored.get(key) != bindings.get(key):
            raise ValueError(f"sealed inference binding mismatch: {key}")
    if sealed.get("fixed_models") != [label for label, _, _ in models]:
        raise ValueError("sealed inference fixed-model list mismatch")


def _scans_for_ids(joint, index, session_ids, point):
    scans = []
    for session_id in session_ids:
        cache = index.get(session_id)
        if cache is None:
            raise ValueError(f"no stable cache for {session_id}")
        evidence, arrays = joint.load_scan_cache(cache, session_id)
        predictions = [
            joint.prediction_for_track(
                evidence, arrays, track, point["latitude_deg"], point["longitude_deg"]
            )
            for track in evidence["tracks"]
        ]
        scans.append((session_id, predictions))
    return scans


def _point_rows(joint, index, session_ids, points, models):
    rows = []
    for point in points:
        scans = _scans_for_ids(joint, index, session_ids, point)
        for label, penalty, hard_shared in models:
            value = score_location(scans, penalty, hard_shared)
            rows.append({**point, "label": label, "penalty_hz2_per_s2": penalty, **value})
    return rows


def _window_results(joint, index, partition, points, selected_label, models):
    model = next(value for value in models if value[0] == selected_label)
    baseline = next(value for value in models if value[0] == "lambda_0")
    output = {}
    for tier in ("single_300s", "about_1h", "about_3h", "about_8h"):
        windows = partition["duration_tiers"][tier]["windows"]
        entries = []
        for window in windows:
            rows = _point_rows(joint, index, window["session_ids"], points, (model, baseline))
            selected = select_by_training([row for row in rows if row["label"] == selected_label])
            zero = select_by_training([row for row in rows if row["label"] == "lambda_0"])
            selected = {
                **selected,
                "reference_error_km": joint.haversine_km(
                    (selected["latitude_deg"], selected["longitude_deg"]), REFERENCE
                ),
            }
            zero = {
                **zero,
                "reference_error_km": joint.haversine_km(
                    (zero["latitude_deg"], zero["longitude_deg"]), REFERENCE
                ),
            }
            entries.append(
                {
                    "window_id": window["window_id"],
                    "scan_count": window["scan_count"],
                    "summed_nominal_capture_seconds": window["summed_nominal_capture_seconds"],
                    "elapsed_span_seconds": window["elapsed_span_seconds"],
                    "selected_regularized": selected,
                    "lambda_0": zero,
                }
            )
        output[tier] = entries
    return output


def run(args):
    if args.validation_only and not (args.output / "inference.json").is_file():
        raise ValueError("validation-only replay requires sealed inference.json")
    if not args.validation_only and any(
        (args.output / name).exists() for name in ("inference.json", "results.json")
    ):
        raise ValueError("fresh numerical output required")
    if args.validation_only and (args.output / "results.json").exists():
        raise ValueError("move prior results.json before validation-only replay")
    started = time.monotonic()
    joint, joint_source = _joint_module()
    dataset = json.loads(args.manifest.read_text())
    points = json.loads(args.locations.read_text())[:3]
    _validate_points(points)
    training_ids = dataset["partitions"]["training"]["session_ids"][:48]
    validation = dataset["partitions"]["development_validation"]
    if len(training_ids) != 48 or validation["session_count"] != 49:
        raise ValueError("expected frozen first-48 training IDs and 49 validation IDs")
    index, cache_digests = _cache_index(args.replication_root)
    models = [(f"lambda_{int(x)}", x, False) for x in LAMBDAS] + [("hard_shared", 0.0, True)]
    bindings = {
        "dataset_manifest_sha256": "sha256:"
        + hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "locations_sha256": "sha256:" + hashlib.sha256(args.locations.read_bytes()).hexdigest(),
        "cache_manifests": cache_digests,
        "joint_source_sha256": "sha256:" + hashlib.sha256(joint_source.read_bytes()).hexdigest(),
        "regularized_source_sha256": "sha256:"
        + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if args.validation_only:
        sealed = json.loads((args.output / "inference.json").read_text())
        _validate_sealed_inputs(sealed, bindings, models)
        training_rows = sealed["training_fixed_point_scores"]
        selected = sealed["sealed_choice"]
    else:
        training_rows = _point_rows(joint, index, training_ids, points, models)
        selected = select_by_reserved(training_rows)
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.validation_only:
        inference = {
            "schema": "regularized-timing-inference/v1",
            "position_truth_used_for_selection": False,
            "training_session_ids": training_ids,
            "model_selection": (
                "minimum randomized reserved-row capped RMS across three fixed points "
                "and listed penalties"
            ),
            "fixed_models": [label for label, _, _ in models],
            "training_fixed_point_scores": training_rows,
            "sealed_choice": selected,
            "bindings": bindings,
        }
        (args.output / "inference.json").write_text(
            json.dumps(inference, indent=2, allow_nan=False) + "\n"
        )
    # The validation state bank is intentionally first opened only after inference.json is sealed.
    validation_windows = _window_results(
        joint, index, validation, points, selected["label"], models
    )
    results = {
        "schema": "regularized-timing/v1",
        "position_truth_used_for_selection": False,
        "candidate_scope": "conditional per-scan production winner union; not full catalogue",
        "fixed_points": "first three original 16-scan finalists; no position search",
        "validation_replay_only": args.validation_only,
        "sealed_inference_payload_sha256": "sha256:"
        + hashlib.sha256((args.output / "inference.json").read_bytes()).hexdigest(),
        "model": {
            "identity_and_cfo": "per-track, profiled only on randomized training rows",
            "tau": (
                "integer seconds -5..5; per-track tau minimizes train MSE + "
                "lambda*(tau-scan_clock)^2"
            ),
            "scan_clock": (
                "latent shared timing center on integer grid -5..5, profiled per scan; "
                "not a physical UTC clock estimate"
            ),
            "hard_shared_control": "tau_track equals scan_clock exactly",
            "location_metric": (
                "duration-weighted capped (800 Hz) RMS; cap is not used for profile selection"
            ),
            "objective_note": (
                "shared-center profile uses equal-track raw MSE plus penalty; "
                "location ranking is a separate unpenalized capped-RMS heuristic, not joint MAP"
            ),
        },
        "training": {
            "session_count": 48,
            "fixed_point_scores": training_rows,
            "sealed_choice": selected,
        },
        "retrospective_validation": validation_windows,
        "reference_error_km": joint.haversine_km(
            (selected["latitude_deg"], selected["longitude_deg"]), REFERENCE
        ),
        "bindings": bindings,
        "runtime_s": time.monotonic() - started,
    }
    (args.output / "results.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    fig, ax = plt.subplots(figsize=(8, 4), layout="constrained")
    for label, _, _ in models:
        values = [row for row in training_rows if row["label"] == label]
        ax.plot(
            [row["location_id"] for row in values],
            [row["reserved_capped_weighted_rms_hz"] for row in values],
            marker="o",
            label=label,
        )
    ax.set_ylabel("randomized reserved capped RMS (Hz)")
    ax.set_xlabel("fixed development point")
    ax.legend(ncol=2, fontsize=8)
    fig.savefig(args.output / "training_selection.png", dpi=160)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--replication-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-only", action="store_true")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
