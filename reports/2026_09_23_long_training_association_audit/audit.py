#!/usr/bin/env python3
"""TRAIN-only candidate-gap and fixed-assignment association diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

import numpy as np

LIGHT_KM_S = 299_792.458
RF_HZ = 11_200_000_000.0
BINS = (
    ("3-10s", 3.0, 10.0),
    ("10-20s", 10.0, 20.0),
    ("20-30s", 20.0, 30.0),
    ("30+s", 30.0, float("inf")),
)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values):
    values = np.asarray(values, dtype=float)
    return (
        {
            key: float(np.quantile(values, q))
            for key, q in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9), ("max", 1.0))
        }
        if len(values)
        else None
    )


def load_single(path):
    spec = importlib.util.spec_from_file_location("sealed_single", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def audit_track(single, cache, track, receiver, up):
    times = np.asarray(track["times_s"], dtype=float)
    mask = np.asarray(track["training_mask"], dtype=bool)
    position, velocity = single.interpolate_track(
        cache["position_ecef_km"],
        cache["velocity_ecef_km_s"],
        cache["receive_plus_tau_offset_ns"],
        times,
    )
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=-1)
    prediction = -RF_HZ / LIGHT_KM_S * np.sum(delta * velocity, axis=-1) / distance
    visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=1) >= 0
    residual = np.asarray(track["measured_hz"], dtype=float)[None, :] - prediction
    offsets = np.mean(residual[:, mask], axis=1)
    errors = residual - offsets[:, None]
    rms = np.sqrt(np.mean(errors[:, mask] ** 2, axis=1))
    rms = np.where(visible, rms, np.inf)
    finite = np.flatnonzero(np.isfinite(rms))
    duration = float(times[-1] - times[0])
    weight = int(len(np.unique(np.floor(times))))
    base = {
        "track_id": track["track_id"],
        "duration_s": duration,
        "weight_s": weight,
        "visible_candidate_count": int(len(finite)),
    }
    if not len(finite):
        return {**base, "status": "unmatched", "training_capped_sse": weight * 800.0**2}
    ordered = finite[np.argsort(rms[finite], kind="stable")]
    first = int(ordered[0])
    held = errors[first, ~mask]
    return {
        **base,
        "status": "matched",
        "candidate_id": int(cache["candidate_id"][first]),
        "first_training_rms_hz": float(rms[first]),
        "second_training_rms_hz": float(rms[ordered[1]]) if len(ordered) > 1 else None,
        "first_second_gap_hz": float(rms[ordered[1]] - rms[first]) if len(ordered) > 1 else None,
        "fixed_assignment_held_rms_hz": float(np.sqrt(np.mean(held**2))),
        "training_capped_sse": weight * min(800.0, float(rms[first])) ** 2,
    }


def summarize(rows):
    matched = [row for row in rows if row["status"] == "matched"]
    total_sse, total_weight = (
        sum(row["training_capped_sse"] for row in rows),
        sum(row["weight_s"] for row in rows),
    )
    bins = []
    for name, low, high in BINS:
        selected = [row for row in rows if low <= row["duration_s"] < high]
        sse, weight = (
            sum(row["training_capped_sse"] for row in selected),
            sum(row["weight_s"] for row in selected),
        )
        bins.append(
            {
                "span_bin": name,
                "track_count": len(selected),
                "weight_s": weight,
                "capped_objective_share": sse / total_sse if total_sse else None,
                "weight_share": weight / total_weight if total_weight else None,
            }
        )
    short = bins[0]
    return {
        "track_count": len(rows),
        "matched_track_count": len(matched),
        "unmatched_track_count": len(rows) - len(matched),
        "training_first_second_gap_hz": quantiles(
            [
                row["first_second_gap_hz"]
                for row in matched
                if row["first_second_gap_hz"] is not None
            ]
        ),
        "fixed_assignment_held_rms_hz": quantiles(
            [row["fixed_assignment_held_rms_hz"] for row in matched]
        ),
        "span_bins": bins,
        "short_track_capped_share_exceeds_weight_share": short["capped_objective_share"]
        > short["weight_share"]
        if short["capped_objective_share"] is not None
        else None,
        "candidate_recurrence_top10": [
            {"candidate_id": key, "track_count": value}
            for key, value in Counter(row["candidate_id"] for row in matched).most_common(10)
        ],
    }


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    inference = json.loads(args.inference.read_text())
    results = json.loads(args.results.read_text())
    cohort = json.loads(args.manifest.read_text())
    if (
        hashlib.sha256(args.inference.read_bytes()).hexdigest()
        != args.inference_sha.read_text().strip()
        or hashlib.sha256(args.results.read_bytes()).hexdigest()
        != args.results_sha.read_text().strip()
    ):
        raise ValueError("sealed input hash mismatch")
    train = cohort["partitions"]["train"]["session_ids"][:16]
    if [x["session_id"] for x in inference["bindings"]["sessions"]] != train:
        raise ValueError("sealed sessions are not frozen first-16 TRAIN IDs")
    single = load_single(args.single_tool)
    caches = {}
    for binding in inference["bindings"]["sessions"]:
        sid = binding["session_id"]
        base = args.cache_root / sid
        if (
            digest(base / "cache_receipt.json") != binding["receipt"]
            or digest(base / "state_cache.npz") != binding["cache"]
        ):
            raise ValueError(f"cache binding mismatch: {sid}")
        receipt = json.loads((base / "cache_receipt.json").read_text())
        caches[sid] = (
            {k: v for k, v in np.load(base / "state_cache.npz", allow_pickle=False).items()},
            receipt["prepared_evidence"]["tracks"],
        )
    views = []
    for sealed_view, result_view in zip(inference["views"], results["views"], strict=True):
        per_prior = {}
        for sealed_search, _result_search in zip(
            sealed_view["searches"], result_view["searches"], strict=True
        ):
            selected = sealed_search["selected"]
            receiver, up = single.receiver_ecef(selected["latitude_deg"], selected["longitude_deg"])
            rows = []
            for sid in sealed_view["session_ids"]:
                cache, tracks = caches[sid]
                rows += [
                    {"session_id": sid, **audit_track(single, cache, track, receiver, up)}
                    for track in tracks
                ]
            per_prior[sealed_search["prior"]] = {
                "selected_coordinate": {
                    "latitude_deg": selected["latitude_deg"],
                    "longitude_deg": selected["longitude_deg"],
                },
                "summary": summarize(rows),
                "assignments": rows,
            }
        left, right = per_prior["sacramento"]["assignments"], per_prior["reno"]["assignments"]
        pairs = [
            (a, b)
            for a, b in zip(left, right, strict=True)
            if a["status"] == b["status"] == "matched"
        ]
        views.append(
            {
                "scan_count": sealed_view["scan_count"],
                "priors": per_prior,
                "sacramento_reno_identity_agreement": {
                    "common_matched_track_count": len(pairs),
                    "same_candidate_count": sum(
                        a["candidate_id"] == b["candidate_id"] for a, b in pairs
                    ),
                    "same_candidate_fraction": sum(
                        a["candidate_id"] == b["candidate_id"] for a, b in pairs
                    )
                    / len(pairs)
                    if pairs
                    else None,
                },
            }
        )
    result = {
        "schema": "long-training-association-audit/v1",
        "scope": {
            "train_only": True,
            "geographic_optimization": False,
            "candidate_gap_interpretation": "training RMS gap is not a calibrated probability",
            "held_scoring": "after fixed training assignments only",
            "truth_or_validation_used": False,
        },
        "views": views,
        "bindings": {
            "tool": digest(Path(__file__)),
            "inference": digest(args.inference),
            "results": digest(args.results),
            "manifest": digest(args.manifest),
            "single_tool": digest(args.single_tool),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(json.dumps({"views": len(views), "train_ids": len(train)}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in (
        "inference",
        "inference_sha",
        "results",
        "results_sha",
        "manifest",
        "cache_root",
        "single_tool",
        "output",
    ):
        p.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    run(p.parse_args())


if __name__ == "__main__":
    main()
