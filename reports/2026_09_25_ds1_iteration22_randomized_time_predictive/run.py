#!/usr/bin/env python3
"""Prototype the DS1 randomized-time zero-rate versus TRAIN-rate scorer."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
DATASET = ROOT / "reports/2026_09_24_ds1/dataset.json"
DS1_RUNNER = ROOT / "reports/2026_09_24_ds1/run.py"
ORBIT = ROOT / "reports/2026_09_24_ds1_orbit_arm/run.py"
GROUPS = ("20260921_00", "20260921_16")
CASE_IDS = {group: f"train_{group}_6" for group in GROUPS}
SEEDS = {
    group: ROOT / f"reports/2026_09_24_ds1/inference/train_{group}_6__reno.json" for group in GROUPS
}
CAP_HZ = 800.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_BOUND_S_H = 0.25
RATE_XATOL_S_H = 2e-7
ROBUST_SCALE_HZ = 250.0


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def verified_json(path: Path, seal: Path | None = None) -> dict[str, Any]:
    if seal is None:
        seal = path.with_suffix(path.suffix + ".sha256")
    expected = seal.read_text().strip().split()[0]
    if digest(path).split(":", 1)[1] != expected:
        raise ValueError(f"seal mismatch: {path}")
    return json.loads(path.read_text())


def load_case(group: str) -> dict[str, Any]:
    dataset = json.loads(DATASET.read_text())
    case = next(row for row in dataset["cases"] if row["case_id"] == CASE_IDS[group])
    if (
        case["partition"] != "train"
        or case["group_id"] != group
        or case["scan_count"] != 6
        or len(case["session_ids"]) != 6
    ):
        raise ValueError("unexpected DS1 case contract")
    return case


def load_train_selected_point(group: str) -> dict[str, float]:
    source = verified_json(SEEDS[group], SEEDS[group].with_suffix(".sha256"))
    if (
        source.get("complete") is not True
        or source.get("held_used_for_fit") is not False
        or source.get("truth_used_for_fit") is not False
        or source.get("case_id") != CASE_IDS[group]
        or source.get("prior") != "reno"
    ):
        raise ValueError("seed is not a sealed TRAIN-only DS1 inference")
    winner = source["models"]["shared_time"]
    return {
        "latitude_deg": float(winner["latitude_deg"]),
        "longitude_deg": float(winner["longitude_deg"]),
        "tau_s": float(winner["tau_s"]),
    }


def unsupported_by_session(engine: Any, assignments: list[dict[str, Any]]) -> dict[str, Any]:
    selected = {(str(row["session_id"]), str(row["track_id"])) for row in assignments}
    sessions: dict[str, dict[str, float | int]] = {}
    for session in engine.sessions:
        sid = str(session["session_id"])
        missing = [
            track for track in session["tracks"] if (sid, str(track["track_id"])) not in selected
        ]
        sessions[sid] = {
            "track_count": len(missing),
            "occupied_second_weight": float(sum(track["weight"] for track in missing)),
        }
    return sessions


def score_rates(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    rates_by_source: dict[str, float],
    unsupported: dict[str, Any],
) -> dict[str, Any]:
    """Fit CFO on TRAIN only and score TRAIN/HELD without cross-mask leakage."""
    source_names, source_index = np.unique(data.source.astype(str), return_inverse=True)
    if set(rates_by_source) != set(source_names):
        raise ValueError("rate/source membership mismatch")
    rates = np.asarray([float(rates_by_source[name]) for name in source_names], float)
    phase = data.age_h * rates[source_index]
    prediction = orbit.doppler(
        receiver,
        orbit.quartic(data.p_nodes, phase),
        orbit.quartic(data.v_nodes, phase),
        search,
    )
    raw = data.y - prediction
    track_names, track_index = np.unique(data.track.astype(str), return_inverse=True)
    offsets = np.empty(len(track_names), float)
    session_rows: dict[str, dict[str, Any]] = {}
    track_rows = []
    for index, track in enumerate(track_names):
        rows = track_index == index
        train = rows & data.train
        held = rows & ~data.train
        if not np.any(train) or not np.any(held):
            raise ValueError(f"track lacks TRAIN or HELD rows: {track}")
        offsets[index] = float(np.mean(raw[train]))
        error = raw[rows] - offsets[index]
        local_train = data.train[rows]
        train_rms = float(np.sqrt(np.mean(error[local_train] ** 2)))
        held_rms = float(np.sqrt(np.mean(error[~local_train] ** 2)))
        sid = str(data.session[np.flatnonzero(rows)[0]])
        if not np.all(data.session[rows].astype(str) == sid):
            raise ValueError("track crosses recording sessions")
        weight = float(data.weights[str(track)])
        item = session_rows.setdefault(
            sid,
            {
                "session_id": sid,
                "supported_track_count": 0,
                "unsupported_track_count": int(unsupported[sid]["track_count"]),
                "supported_weight": 0.0,
                "unsupported_weight": float(unsupported[sid]["occupied_second_weight"]),
                "train_numerator": float(unsupported[sid]["occupied_second_weight"]),
                "held_numerator": float(unsupported[sid]["occupied_second_weight"]),
            },
        )
        item["supported_track_count"] += 1
        item["supported_weight"] += weight
        item["train_numerator"] += weight * min((train_rms / CAP_HZ) ** 2, 1.0)
        item["held_numerator"] += weight * min((held_rms / CAP_HZ) ** 2, 1.0)
        track_rows.append(
            {
                "track_id": str(track),
                "session_id": sid,
                "source": str(data.source[np.flatnonzero(rows)[0]]),
                "train_observations": int(train.sum()),
                "held_observations": int(held.sum()),
                "occupied_second_weight": weight,
                "training_cfo_hz": offsets[index],
                "training_rms_hz": train_rms,
                "held_rms_hz": held_rms,
            }
        )
    sessions = []
    for sid in sorted(unsupported):
        if sid not in session_rows:
            missing = unsupported[sid]
            if not missing["track_count"]:
                raise ValueError("session has no scored tracks")
            session_rows[sid] = {
                "session_id": sid,
                "supported_track_count": 0,
                "unsupported_track_count": int(missing["track_count"]),
                "supported_weight": 0.0,
                "unsupported_weight": float(missing["occupied_second_weight"]),
                "train_numerator": float(missing["occupied_second_weight"]),
                "held_numerator": float(missing["occupied_second_weight"]),
            }
        row = session_rows[sid]
        denominator = row["supported_weight"] + row["unsupported_weight"]
        if denominator <= 0:
            raise ValueError("session denominator is empty")
        sessions.append(
            {
                **{k: v for k, v in row.items() if not k.endswith("_numerator")},
                "occupied_second_weight": denominator,
                "training_capped_loss": row["train_numerator"] / denominator,
                "held_capped_loss": row["held_numerator"] / denominator,
            }
        )
    return {
        "equal_session_training_capped_loss": float(
            np.mean([row["training_capped_loss"] for row in sessions])
        ),
        "equal_session_held_capped_loss": float(
            np.mean([row["held_capped_loss"] for row in sessions])
        ),
        "session_scores": sessions,
        "track_scores": track_rows,
    }


def fit_train_rates(data: Any, receiver: np.ndarray, search: Any, orbit: Any) -> dict[str, Any]:
    """Fit independent per-source rates from TRAIN rows and TRAIN CFOs only."""
    source_names, source_index = np.unique(data.source.astype(str), return_inverse=True)
    fitted: dict[str, float] = {}
    rows_out = []
    for source_index_value, source in enumerate(source_names):
        source_rows = source_index == source_index_value
        tracks = np.unique(data.track[source_rows].astype(str))
        selected_rows = np.flatnonzero(source_rows)
        selected_tracks = tuple(str(track) for track in tracks)

        def objective(
            rate: float,
            rows: np.ndarray = selected_rows,
            local_tracks: tuple[str, ...] = selected_tracks,
        ) -> float:
            phase = data.age_h[rows] * float(rate)
            prediction = orbit.doppler(
                receiver,
                orbit.quartic(data.p_nodes[rows], phase),
                orbit.quartic(data.v_nodes[rows], phase),
                search,
            )
            raw = data.y[rows] - prediction
            local_track = data.track[rows].astype(str)
            local_train = data.train[rows]
            errors = []
            for track in local_tracks:
                selected = local_track == track
                training = selected & local_train
                if not np.any(training):
                    raise ValueError(f"source track lacks TRAIN rows: {track}")
                cfo = float(np.mean(raw[training]))
                errors.append(raw[training] - cfo)
            error = np.concatenate(errors)
            z = error / ROBUST_SCALE_HZ
            return float(
                np.sum(np.sqrt(1.0 + z * z) - 1.0) + 0.5 * (float(rate) / RATE_SIGMA_S_H) ** 2
            )

        result = minimize_scalar(
            objective,
            bounds=(-RATE_BOUND_S_H, RATE_BOUND_S_H),
            method="bounded",
            options={"xatol": RATE_XATOL_S_H, "maxiter": 100},
        )
        fitted[str(source)] = float(result.x)
        rows_out.append(
            {
                "source": str(source),
                "rate_s_h": float(result.x),
                "training_objective": float(result.fun),
                "converged": bool(result.success),
                "iterations": int(result.nfev),
                "message": str(result.message),
            }
        )
    return {
        "rates_s_h": fitted,
        "sources": rows_out,
        "converged": all(row["converged"] for row in rows_out),
        "source_count": len(rows_out),
        "rate_bound_s_h": RATE_BOUND_S_H,
        "rate_xatol_s_h": RATE_XATOL_S_H,
        "effective_boundary_rate_count": sum(
            abs(row["rate_s_h"]) >= RATE_BOUND_S_H - max(5 * RATE_XATOL_S_H, 1e-6)
            for row in rows_out
        ),
    }


def run_group(group: str) -> dict[str, Any]:
    begun = time.perf_counter()
    ds1 = load_module(DS1_RUNNER, f"i22_ds1_{group}")
    orbit = load_module(ORBIT, f"i22_orbit_{group}")
    case = load_case(group)
    point = load_train_selected_point(group)
    _clock, engine = ds1.make_engine(case)
    # The original DS1 engine verifies each receipt/cache pair but does not
    # retain the directory in its session dictionary.  The exact orbit builder
    # needs that already-verified directory to read causal TLE provenance.
    for session in engine.sessions:
        session["cache_path"] = str(ds1.CACHE_ROOTS[group] / session["session_id"])
    data = orbit.prepare(
        engine,
        point["latitude_deg"],
        point["longitude_deg"],
        point["tau_s"],
    )
    receiver, _up = engine.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    unsupported = unsupported_by_session(engine, data.assignments)
    sources = tuple(sorted(np.unique(data.source.astype(str))))
    zero_rates = {source: 0.0 for source in sources}
    zero_score = score_rates(data, receiver, engine.search, orbit, zero_rates, unsupported)
    fit = fit_train_rates(data, receiver, engine.search, orbit)
    fitted_rates = fit["rates_s_h"]
    rate_score = score_rates(data, receiver, engine.search, orbit, fitted_rates, unsupported)
    zero_gate = orbit.exact_replay_gate(
        data, receiver, engine.search, point["tau_s"], zero_rates, tolerance_hz=0.2
    )
    rate_gate = orbit.exact_replay_gate(
        data, receiver, engine.search, point["tau_s"], fitted_rates, tolerance_hz=0.2
    )
    return {
        "group_id": group,
        "case_id": case["case_id"],
        "fixed_point": point,
        "mask_counts": {
            "training_observations": int(data.train.sum()),
            "held_observations": int((~data.train).sum()),
            "supported_tracks": len(data.weights),
            "unsupported_tracks": int(sum(row["track_count"] for row in unsupported.values())),
            "sessions": len(np.unique(data.session.astype(str))),
            "sources": len(sources),
        },
        "identity_selection": "ordinary DS1 hard association on randomized TRAIN rows only",
        "zero_rate": {"score": zero_score, "exact_sgp4_gate": zero_gate},
        "train_rate": {
            "score": rate_score,
            "exact_sgp4_gate": rate_gate,
            "fit": fit,
        },
        "held_delta_rate_minus_zero": (
            rate_score["equal_session_held_capped_loss"]
            - zero_score["equal_session_held_capped_loss"]
        ),
        "bindings": {
            "seed": digest(SEEDS[group]),
            "session_bindings": engine.bindings,
        },
        "elapsed_s": time.perf_counter() - begun,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    plan = verified_json(PLAN)
    if (
        plan.get("status") != "prototype-only-no-geographic-search"
        or plan.get("reference_used_for_inference") is not False
    ):
        raise ValueError("plan does not authorize this smoke prototype")
    groups = [run_group(group) for group in GROUPS]
    output = {
        "schema": "ds1-iteration22-randomized-time-predictive-smoke/v1",
        "complete": True,
        "reference_used": False,
        "held_used_for_selection": False,
        "geographic_search_run": False,
        "groups": groups,
        "summary": {
            "group_count": len(groups),
            "zero_better_held_group_count": sum(
                row["held_delta_rate_minus_zero"] >= 0 for row in groups
            ),
            "rate_better_held_group_count": sum(
                row["held_delta_rate_minus_zero"] < 0 for row in groups
            ),
        },
        "bindings": {
            "plan": digest(PLAN),
            "dataset": digest(DATASET),
            "runner": digest(Path(__file__)),
            "ds1_runner": digest(DS1_RUNNER),
            "orbit": digest(ORBIT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, indent=2, sort_keys=True) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "summary": output["summary"],
                "held_deltas": {
                    row["group_id"]: row["held_delta_rate_minus_zero"] for row in groups
                },
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
