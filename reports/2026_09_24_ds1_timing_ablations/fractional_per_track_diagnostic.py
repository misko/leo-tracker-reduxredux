#!/usr/bin/env python3
# ruff: noqa: E501
"""Historical per-track fractional timing, retained as a DS1 diagnostic only."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("timing_ablations", HERE / "run.py")
timing = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(timing)


def fractional_track(engine, item, lat, lon):
    """Fit one fixed identity's tau in a 0.25 s interval from TRAIN rows only."""
    track, session = item["track"], item["session"]
    if item["candidate_index"] is None:
        return {"weight": track["weight"], "train": 1.0, "held": 1.0, "tau_s": None}
    index = item["candidate_index"]
    receiver, up = engine.search.receiver_ecef(lat, lon)
    single = {
        **session,
        "position": session["position"][index : index + 1],
        "velocity": session["velocity"][index : index + 1],
    }
    p, v = engine.interpolate(single, track["times"], timing.TAUS)
    delta = p[0] - receiver
    distance = np.linalg.norm(delta, axis=-1)
    visible = np.max(np.sum(delta * up, axis=-1) / distance, axis=0) >= 0
    prediction = (
        -engine.search.REFERENCE_RF_HZ
        / engine.search.LIGHT_KM_S
        * np.sum(delta * v[0], axis=-1)
        / distance
    )
    # prediction is observation x timing-node.  This is the historical linear
    # profile inside every quarter-second node, with a constant TRAIN CFO.
    train = track["train"]
    y = track["measured"][train]
    m0 = prediction[train, :-1].T
    slope = np.diff(prediction[train], axis=1).T
    residual = y[None, :] - m0
    residual -= residual.mean(axis=1, keepdims=True)
    centered_slope = slope - slope.mean(axis=1, keepdims=True)
    denominator = np.sum(centered_slope**2, axis=1)
    alpha = np.divide(
        np.sum(residual * centered_slope, axis=1),
        denominator,
        out=np.zeros_like(denominator),
        where=denominator > 0,
    )
    alpha = np.clip(alpha, 0.0, 1.0)
    fitted = m0 + alpha[:, None] * slope
    cfo = np.mean(y[None, :] - fitted, axis=1)
    mse = np.mean((y[None, :] - fitted - cfo[:, None]) ** 2, axis=1)
    mse = np.where(visible[:-1], mse, np.inf)
    interval = int(np.argmin(mse))
    if not np.isfinite(mse[interval]):
        return {"weight": track["weight"], "train": 1.0, "held": 1.0, "tau_s": None}
    held_prediction = prediction[~train, interval] + alpha[interval] * (
        prediction[~train, interval + 1] - prediction[~train, interval]
    )
    held_mse = float(np.mean((track["measured"][~train] - held_prediction - cfo[interval]) ** 2))
    return {
        "weight": track["weight"],
        "train": min(float(mse[interval]) / 800.0**2, 1.0),
        "held": min(held_mse / 800.0**2, 1.0),
        "tau_s": float(timing.TAUS[interval] + 0.25 * alpha[interval]),
        "candidate_id": item["candidate_id"],
    }


def point(engine, source, location):
    lat, lon = location["latitude_deg"], location["longitude_deg"]
    fixed = timing.fixed_tracks(engine, lat, lon)
    # No held data enter this loop or alter its selected identity/tau/CFO.
    selected = [fractional_track(engine, item, lat, lon) for item in fixed]
    denominator = sum(x["weight"] for x in selected)
    return {
        "model": "historical_fractional_per_track_tau_diagnostic",
        "latitude_deg": lat,
        "longitude_deg": lon,
        "geographic_point_role": location["from_model"],
        "training_capped_loss": sum(x["weight"] * x["train"] for x in selected) / denominator,
        "held_capped_loss": sum(x["weight"] * x["held"] for x in selected) / denominator,
        "track_count": len(selected),
        "fixed_identity_count": sum(x.get("candidate_id") is not None for x in selected),
        "per_track_tau_s": [x["tau_s"] for x in selected],
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        required=True,
        choices=(
            "train_20260921_00_16",
            "train_20260921_16_16",
            "validation_20260922_08_16",
            "validation_20260921_08_16",
            "train_20260921_00_all",
            "train_20260921_16_all",
        ),
    )
    args = parser.parse_args()
    ids = {args.case}
    rows = []
    for case in json.loads(timing.DATA.read_text())["cases"]:
        if case["case_id"] not in ids:
            continue
        for prior in ("sacramento", "reno"):
            arm = timing.sealed(timing.DS1 / "inference" / f"{case['case_id']}__{prior}.json")
            module, engine = timing.load(timing.SOURCE, "fractional_ds1_source"), None
            _, engine = module.make_engine(case)
            for location in timing.terminal_union(arm):
                rows.append(
                    {
                        "case_id": case["case_id"],
                        "partition": case["partition"],
                        "group_id": case["group_id"],
                        "scan_count": case["scan_count"],
                        "view": case["view"],
                        "prior": prior,
                        "status": "completed",
                        **point(engine, arm, location),
                    }
                )
    output = {
        "schema": "ds1-historical-fractional-per-track-diagnostic/v1",
        "rows": rows,
        "scope": "four non-TEST 16-scan groups plus two complete TRAIN blocks; fixed identities at inherited DS1 terminal point union",
        "timing": "independent per-track tau in [-5,5] on 0.25 s nodes, linearly profiled inside each interval",
        "diagnostic_only": True,
        "held_used_for_fit": False,
        "truth_used_for_fit": False,
        "bindings": {
            "source": timing.digest(Path(__file__)),
            "shared_harness": timing.digest(HERE / "run.py"),
            "ds1_dataset": timing.digest(timing.DATA),
        },
    }
    path = HERE / f"fractional_per_track_{args.case}.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    print(json.dumps({"rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
