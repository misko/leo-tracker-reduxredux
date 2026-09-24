#!/usr/bin/env python3
# ruff: noqa: E501
"""DS1 timing controls, deliberately isolated from the orbit-model work.

The only input selected here is each DS1 paired inference's TRAIN-only terminal
geographic point union.  At every such point identities are frozen from the
original tau=0, randomized-TRAIN assignment before any timing profiling.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
DS1 = ROOT / "reports/2026_09_24_ds1"
SOURCE = DS1 / "run.py"
DATA = DS1 / "dataset.json"
MISSING = "scan-hop-6cd2560365a058bc"
SCALES = (0.2, 1.0, 5.0)
TAUS = np.arange(-5.0, 5.0001, 0.25)


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sealed(path: Path):
    if (
        hashlib.sha256(path.read_bytes()).hexdigest()
        != path.with_suffix(".sha256").read_text().strip()
    ):
        raise ValueError(f"unsealed DS1 input: {path}")
    return json.loads(path.read_text())


def cases():
    """Two full TRAIN blocks, two full validation blocks, and nested TRAIN views.

    The full TEST64 case is included for its required explicit authority failure.
    This is the declared coverage rather than an implicit sample of cases.
    """
    all_cases = json.loads(DATA.read_text())["cases"]
    ids = {
        "train_20260921_00_1",
        "train_20260921_00_6",
        "train_20260921_00_16",
        "train_20260921_00_all",
        "train_20260921_16_all",
        "validation_20260922_08_all",
        "validation_20260921_08_all",
        "test_20260922_00_all",
    }
    chosen = [x for x in all_cases if x["case_id"] in ids]
    if {x["case_id"] for x in chosen} != ids:
        raise ValueError("DS1 requested coverage changed")
    return chosen


def terminal_union(arm):
    """The two terminal points of DS1's accumulated baseline/shared point union."""
    last = arm["levels"][-1]
    result = []
    for model in ("baseline", "shared"):
        point = last[model]
        key = (float(point["latitude_deg"]), float(point["longitude_deg"]))
        if key not in {(x["latitude_deg"], x["longitude_deg"]) for x in result}:
            result.append({"latitude_deg": key[0], "longitude_deg": key[1], "from_model": model})
    return result


def fixed_tracks(engine, lat, lon):
    """Freeze one identity per track using tau-zero randomized TRAIN rows only."""
    _, _, groups = engine.profile(lat, lon, np.array([0.0]), False, True)
    assigned = {(x["session_id"], x["track_id"]): x["candidate_id"] for x in groups[0]}
    output = []
    for session in engine.sessions:
        index = {str(value): i for i, value in enumerate(session["candidate_ids"])}
        for track in session["tracks"]:
            cid = assigned[(session["session_id"], track["track_id"])]
            output.append(
                {
                    "session": session,
                    "track": track,
                    "candidate_id": cid,
                    "candidate_index": index.get(cid),
                }
            )
    return output


def one_track(engine, item, lat, lon, tau):
    """Profile only a constant CFO on original TRAIN rows for a frozen identity."""
    track, session = item["track"], item["session"]
    weight = track["weight"]
    if item["candidate_index"] is None:
        return {"weight": weight, "train": 1.0, "held": 1.0, "candidate_id": None}
    index = item["candidate_index"]
    receiver, up = engine.search.receiver_ecef(lat, lon)
    single = {
        **session,
        "position": session["position"][index : index + 1],
        "velocity": session["velocity"][index : index + 1],
    }
    p, v = engine.interpolate(single, track["times"], np.array([tau]))
    delta = p[0, :, 0] - receiver
    distance = np.linalg.norm(delta, axis=-1)
    visible = bool(np.max(np.sum(delta * up, axis=-1) / distance) >= 0)
    if not visible:
        return {"weight": weight, "train": 1.0, "held": 1.0, "candidate_id": item["candidate_id"]}
    predicted = (
        -engine.search.REFERENCE_RF_HZ
        / engine.search.LIGHT_KM_S
        * np.sum(delta * v[0, :, 0], axis=1)
        / distance
    )
    mask = track["train"]
    offset = float(np.mean(track["measured"][mask] - predicted[mask]))
    error = track["measured"] - predicted - offset
    train = min(float(np.mean(error[mask] ** 2)) / 800.0**2, 1.0)
    held = min(float(np.mean(error[~mask] ** 2)) / 800.0**2, 1.0)
    return {
        "weight": weight,
        "train": train,
        "held": held,
        "candidate_id": item["candidate_id"],
        "cfo_hz": offset,
    }


def global_profile(engine, fixed, lat, lon, taus):
    rows = []
    for tau in taus:
        values = [one_track(engine, item, lat, lon, float(tau)) for item in fixed]
        denominator = sum(x["weight"] for x in values)
        rows.append(
            {
                "tau_s": float(tau),
                "training_capped_loss": sum(x["weight"] * x["train"] for x in values) / denominator,
                "held_capped_loss": sum(x["weight"] * x["held"] for x in values) / denominator,
                "track_rows": values,
            }
        )
    return rows


def choose_global(rows):
    return min(rows, key=lambda x: (x["training_capped_loss"], abs(x["tau_s"]), x["tau_s"]))


def regularized(engine, fixed, lat, lon, scale):
    """One global epoch and a shrinkage-profiled epoch for every scan.

    The likelihood is the DS1 occupied-second weighted, 800-Hz-capped loss.
    The historical scale is a Gaussian-width analogue: each scan pays its
    occupied-second mass times (scan_tau-global_tau)^2 / scale^2.
    """
    by_session = {}
    for item in fixed:
        by_session.setdefault(item["session"]["session_id"], []).append(item)
    scans = {}
    for sid, items in by_session.items():
        grid = global_profile(engine, items, lat, lon, TAUS)
        weight = sum(x["weight"] for x in grid[0]["track_rows"])
        scans[sid] = {"weight": weight, "grid": grid}
    candidates = []
    for global_tau in TAUS:
        chosen, penalized, train_sum, held_sum, denom = [], 0.0, 0.0, 0.0, 0
        for sid, scan in scans.items():
            local = min(
                scan["grid"],
                key=lambda r: (
                    r["training_capped_loss"] + (r["tau_s"] - global_tau) ** 2 / scale**2,
                    abs(r["tau_s"] - global_tau),
                    r["tau_s"],
                ),
            )
            weight = scan["weight"]
            penalty = weight * (local["tau_s"] - global_tau) ** 2 / scale**2
            chosen.append(
                {
                    "session_id": sid,
                    "scan_tau_s": local["tau_s"],
                    "residual_tau_s": local["tau_s"] - float(global_tau),
                }
            )
            penalized += weight * local["training_capped_loss"] + penalty
            train_sum += weight * local["training_capped_loss"]
            held_sum += weight * local["held_capped_loss"]
            denom += weight
        candidates.append(
            {
                "tau_s": float(global_tau),
                "training_capped_loss": train_sum / denom,
                "held_capped_loss": held_sum / denom,
                "penalized_train_objective": penalized / denom,
                "scan_epochs": chosen,
            }
        )
    return min(
        candidates, key=lambda x: (x["penalized_train_objective"], abs(x["tau_s"]), x["tau_s"])
    )


def point_models(engine, point, scales):
    lat, lon = point["latitude_deg"], point["longitude_deg"]
    fixed = fixed_tracks(engine, lat, lon)
    coarse = global_profile(engine, fixed, lat, lon, TAUS)
    shared = choose_global(coarse)
    zero = next(x for x in coarse if x["tau_s"] == 0.0)
    # A common fractional epoch is diagnostic only; it has no per-track freedom.
    fine_taus = np.unique(
        np.round(
            np.arange(
                max(-5, shared["tau_s"] - 0.25), min(5, shared["tau_s"] + 0.25) + 0.001, 0.05
            ),
            10,
        )
    )
    fractional = choose_global(global_profile(engine, fixed, lat, lon, fine_taus))
    models = [
        {"model": "fixed_identity_tau0", **zero},
        {"model": "fixed_identity_shared_global_tau", **shared},
        {"model": "fractional_common_global_tau_diagnostic", **fractional},
    ]
    models.extend(
        {
            "model": f"regularized_global_plus_scan_epoch_scale_{scale:g}s",
            "scale_s": scale,
            **regularized(engine, fixed, lat, lon, scale),
        }
        for scale in scales
    )
    for row in models:
        row.pop("track_rows", None)
        row.update(
            {
                "latitude_deg": lat,
                "longitude_deg": lon,
                "fixed_identity_count": sum(x["candidate_id"] is not None for x in fixed),
                "track_count": len(fixed),
            }
        )
    return models


def infer(case, prior, scales):
    if MISSING in case["session_ids"]:
        return [
            {
                "case_id": case["case_id"],
                "prior": prior,
                "status": "input_failure",
                "model": "all",
                "failure": "missing counter-continuity authority/cache; exact full TEST64 cohort ineligible",
            }
        ]
    arm = sealed(DS1 / "inference" / f"{case['case_id']}__{prior}.json")
    if arm["held_used_for_fit"] or arm["truth_used_for_fit"]:
        raise ValueError("DS1 anchor inference was not train-only")
    ds1 = load(SOURCE, "ds1_timing_source")
    _, engine = ds1.make_engine(case)
    output = []
    for point in terminal_union(arm):
        for row in point_models(engine, point, scales):
            output.append(
                {
                    "case_id": case["case_id"],
                    "partition": case["partition"],
                    "group_id": case["group_id"],
                    "scan_count": case["scan_count"],
                    "view": case["view"],
                    "prior": prior,
                    "status": "completed",
                    "geographic_point_role": point["from_model"],
                    "held_used_for_fit": False,
                    "truth_used_for_fit": False,
                    **row,
                }
            )
    return output


def select_scale(rows):
    # The inherited shared-time terminal point is the one TRAIN-only anchor
    # selected for this comparison.  The tau-zero terminal point remains a
    # reported paired sensitivity, not a second vote in hyperparameter choice.
    eligible = [
        r
        for r in rows
        if r.get("status") == "completed"
        and r["partition"] == "train"
        and r["scan_count"] in (72, 79)
        and r["geographic_point_role"] == "shared"
        and r["model"].startswith("regularized_")
    ]
    scores = []
    for scale in SCALES:
        subset = [r for r in eligible if r["scale_s"] == scale]
        if len(subset) != 4:  # two full blocks, two priors, terminal selected point only
            raise ValueError(f"incomplete TRAIN scale coverage for {scale}: {len(subset)}")
        scores.append(
            {
                "scale_s": scale,
                "mean_penalized_train_objective": float(
                    np.mean([r["penalized_train_objective"] for r in subset])
                ),
            }
        )
    return min(scores, key=lambda x: (x["mean_penalized_train_objective"], x["scale_s"])), scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("train", "evaluate"), required=True)
    args = parser.parse_args()
    started = time.monotonic()
    selected_cases = cases()
    if args.phase == "train":
        work = [
            c for c in selected_cases if c["partition"] == "train" and c["scan_count"] in (72, 79)
        ]
        scales = SCALES
    else:
        selection = json.loads((HERE / "scale_selection.json").read_text())
        if selection["bindings"]["source"] != digest(Path(__file__)):
            raise ValueError("source changed after TRAIN scale sealing")
        work = selected_cases
        scales = (selection["selected"]["scale_s"],)
    rows = []
    for case in work:
        for prior in ("sacramento", "reno"):
            rows.extend(infer(case, prior, scales))
    if args.phase == "train":
        selected, scores = select_scale(rows)
        payload = {
            "schema": "ds1-timing-scale-selection/v1",
            "selected": selected,
            "scores": scores,
            "rows": rows,
            "held_used_for_fit": False,
            "truth_used_for_fit": False,
            "bindings": {
                "source": digest(Path(__file__)),
                "ds1_dataset": digest(DATA),
                "ds1_runner": digest(SOURCE),
            },
        }
        (HERE / "scale_selection.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        )
        (HERE / "scale_selection.sha256").write_text(
            hashlib.sha256((HERE / "scale_selection.json").read_bytes()).hexdigest() + "\n"
        )
    else:
        payload = {
            "schema": "ds1-timing-ablations/v1",
            "coverage": {
                "completed_case_ids": [
                    c["case_id"] for c in work if MISSING not in c["session_ids"]
                ],
                "explicit_failure_case_ids": [
                    c["case_id"] for c in work if MISSING in c["session_ids"]
                ],
                "omitted_ds1_cases": "other nested 1/6/16 views outside first TRAIN block; all full blocks plus three nested duration views are covered",
            },
            "rows": rows,
            "held_used_for_fit": False,
            "truth_used_for_fit": False,
            "elapsed_s": time.monotonic() - started,
            "bindings": {
                "source": digest(Path(__file__)),
                "scale_selection": digest(HERE / "scale_selection.json"),
                "ds1_dataset": digest(DATA),
                "ds1_runner": digest(SOURCE),
            },
        }
        (HERE / "results.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"phase": args.phase, "row_count": len(rows), "elapsed_s": time.monotonic() - started},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
