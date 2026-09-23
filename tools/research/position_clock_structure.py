"""Train-only timing-structure diagnostic on three cached development blocks."""

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


def _module():
    path = Path(__file__).with_name("sixteen_joint_compare.py")
    spec = importlib.util.spec_from_file_location("clock_joint", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, path


def _weight(prediction):
    return int(len(np.unique(np.floor(prediction.times_s).astype(int))))


def _rms(weighted):
    weight = sum(w for w, x in weighted)
    return float(np.sqrt(sum(w * x * x for w, x in weighted) / weight))


def _profile(prediction, tau_index):
    """Choose identity/CFO from training rows only at one frozen tau."""
    train = np.asarray(prediction.training_mask, bool)
    residual = (
        np.asarray(prediction.measured_hz)[None, :]
        - np.asarray(prediction.predictions_hz)[:, tau_index, :]
    )
    offset = residual[:, train].mean(axis=1)
    centered = residual - offset[:, None]
    train_rms = np.sqrt(np.mean(centered[:, train] ** 2, axis=1))
    visible = np.asarray(prediction.visible, bool)
    if visible.ndim == 2:
        visible = visible[:, tau_index]
    train_rms = np.where(visible, train_rms, np.inf)
    candidate = int(np.argmin(train_rms))
    if not np.isfinite(train_rms[candidate]):
        return None
    return {
        "tau_s": float(prediction.taus_s[tau_index]),
        "candidate_id": str(prediction.candidate_ids[candidate]),
        "offset_hz": float(offset[candidate]),
        "training_rms_hz": float(train_rms[candidate]),
        "evaluation_rms_hz": float(np.sqrt(np.mean(centered[candidate, ~train] ** 2))),
    }


def score_scan(predictions, structure):
    """Return fixed choices and duration-weighted capped train/evaluation RMS."""
    if structure not in {"per_track_tau", "single_tau_per_scan", "tau_fixed_zero"}:
        raise ValueError("unknown structure")
    taus = np.asarray(predictions[0].taus_s)
    zero = int(np.flatnonzero(np.isclose(taus, 0))[0])
    if structure == "per_track_tau":
        indices = [
            int(
                np.argmin(
                    [
                        (_profile(p, j) or {"training_rms_hz": np.inf})["training_rms_hz"]
                        for j in range(len(taus))
                    ]
                )
            )
            for p in predictions
        ]
    elif structure == "tau_fixed_zero":
        indices = [zero] * len(predictions)
    else:
        values = []
        for j in range(len(taus)):
            rows = [_profile(p, j) for p in predictions]
            values.append(
                sum(
                    _weight(p) * min(800.0, r["training_rms_hz"] if r else 800.0) ** 2
                    for p, r in zip(predictions, rows, strict=True)
                )
            )
        indices = [int(np.argmin(values))] * len(predictions)
    choices = [_profile(p, j) for p, j in zip(predictions, indices, strict=True)]
    train = [
        (_weight(p), min(800.0, r["training_rms_hz"] if r else 800.0))
        for p, r in zip(predictions, choices, strict=True)
    ]
    evaluation = [
        (_weight(p), min(800.0, r["evaluation_rms_hz"] if r else 800.0))
        for p, r in zip(predictions, choices, strict=True)
    ]
    return {
        "training_capped_weighted_rms_hz": _rms(train),
        "evaluation_capped_weighted_rms_hz": _rms(evaluation),
        "choices": choices,
    }


def score_location(scans, structure):
    answers = [score_scan(predictions, structure) for _, predictions in scans]
    train = []
    evaluation = []
    choices = []
    for (_, predictions), answer in zip(scans, answers, strict=True):
        for prediction, choice in zip(predictions, answer["choices"], strict=True):
            train.append(
                (_weight(prediction), min(800.0, choice["training_rms_hz"] if choice else 800.0))
            )
            evaluation.append(
                (_weight(prediction), min(800.0, choice["evaluation_rms_hz"] if choice else 800.0))
            )
            choices.append(choice)
    return {
        "training_capped_weighted_rms_hz": _rms(train),
        "evaluation_capped_weighted_rms_hz": _rms(evaluation),
        "choices": choices,
        "single_tau_per_scan": [
            a["choices"][0]["tau_s"] if a["choices"] and a["choices"][0] else None for a in answers
        ],
    }


def select_location(rows, structure):
    return min(
        (x for x in rows if x["structure"] == structure),
        key=lambda x: x["training_capped_weighted_rms_hz"],
    )


def run(args):
    if args.output.exists():
        raise ValueError("fresh output required")
    joint, source = _module()
    locations = json.loads(args.locations.read_text())[:3]
    blocks = [args.replication_root / f"block_{i:02d}" for i in (1, 2, 3)]
    if not all((x / "cache/cache_manifest.json").is_file() for x in blocks):
        raise ValueError("three stable cached blocks required")
    started = time.monotonic()
    rows = []
    time_bounds = []
    capture_sum = 48 * 300
    for point in locations:
        scans = []
        for block in blocks:
            manifest = json.loads((block / "cache/cache_manifest.json").read_text())
            for scan in manifest["scans"]:
                evidence, arrays = joint.load_scan_cache(block / "cache", scan["session_id"])
                predictions = [
                    joint.prediction_for_track(
                        evidence, arrays, t, point["latitude_deg"], point["longitude_deg"]
                    )
                    for t in evidence["tracks"]
                ]
                scans.append((scan["session_id"], predictions))
                time_bounds.append(int(evidence["start_utc_ns"]))
        for structure in ("per_track_tau", "single_tau_per_scan", "tau_fixed_zero"):
            answer = score_location(scans, structure)
            rows.append(
                {
                    **point,
                    "structure": structure,
                    "scan_count": len(scans),
                    "track_count": sum(len(x[1]) for x in scans),
                    "observation_count": sum(len(p.observation_ids) for _, ps in scans for p in ps),
                    **answer,
                }
            )
    args.output.mkdir(parents=True)
    selected_train = []
    for structure in ("per_track_tau", "single_tau_per_scan", "tau_fixed_zero"):
        winner = select_location(rows, structure)
        selected_train.append(
            {
                "structure": structure,
                "location_id": winner["location_id"],
                "latitude_deg": winner["latitude_deg"],
                "longitude_deg": winner["longitude_deg"],
                "training_objective_hz": winner["training_capped_weighted_rms_hz"],
                "evaluation_capped_weighted_rms_hz": winner["evaluation_capped_weighted_rms_hz"],
                "degrees_of_freedom": {
                    "per_track_tau": "one discrete tau per track",
                    "single_tau_per_scan": "one discrete tau per scan",
                    "tau_fixed_zero": "zero fitted tau",
                }[structure],
            }
        )
    bindings = {
        "locations_sha256": "sha256:" + hashlib.sha256(args.locations.read_bytes()).hexdigest(),
        "cache_manifests": {
            block.name: "sha256:"
            + hashlib.sha256((block / "cache/cache_manifest.json").read_bytes()).hexdigest()
            for block in blocks
        },
        "joint_source_sha256": "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        "clock_source_sha256": "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    inference = {
        "schema": "development-clock-structure-inference/v1",
        "position_truth_used_for_selection": False,
        "bindings": bindings,
        "all_fixed_point_scores": rows,
        "training_selected_models": selected_train,
    }
    (args.output / "inference.json").write_text(
        json.dumps(inference, indent=2, allow_nan=False) + "\n"
    )
    selected = [
        {
            **row,
            "reference_error_km": joint.haversine_km(
                (row["latitude_deg"], row["longitude_deg"]), REFERENCE
            ),
        }
        for row in selected_train
    ]
    document = {
        "schema": "development-clock-structure/v1",
        "position_truth_used_for_selection": False,
        "candidate_scope": "per-scan conditional production winner union; not full catalogue",
        "training_blocks": [x.name for x in blocks],
        "timing_support_s": list(range(-5, 6)),
        "cfo": "one profiled constant CFO per track fitted only on randomized training rows",
        "duration": {
            "capture_start_span_s": (max(time_bounds) - min(time_bounds)) / 1e9,
            "elapsed_window_including_last_nominal_capture_s": (max(time_bounds) - min(time_bounds))
            / 1e9
            + 300,
            "nominal_capture_sum_s": capture_sum,
            "planned_capture_s_per_scan": 300,
            "note": "capture-start span includes gaps; nominal capture sum does not",
        },
        "bindings": bindings,
        "all_fixed_point_scores": rows,
        "training_selected_models": selected,
        "runtime_s": time.monotonic() - started,
    }
    (args.output / "results.json").write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n"
    )
    fig, ax = plt.subplots(figsize=(7, 4), layout="constrained")
    for structure in ("per_track_tau", "single_tau_per_scan", "tau_fixed_zero"):
        values = [x for x in rows if x["structure"] == structure]
        ax.plot(
            [x["location_id"] for x in values],
            [x["training_capped_weighted_rms_hz"] for x in values],
            "o-",
            label=structure,
        )
    ax.set(
        ylabel="Training capped duration-weighted RMS (Hz)",
        xlabel="Fixed original development point",
    )
    ax.grid(alpha=0.25)
    ax.legend()
    fig.savefig(args.output / "training_objectives.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--replication-root", type=Path)
    parser.add_argument("--locations", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.replication_root and args.locations and args.output:
        run(args)
    else:
        parser.error("--replication-root, --locations, --output required")
