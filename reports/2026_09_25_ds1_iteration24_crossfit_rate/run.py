#!/usr/bin/env python3
"""Run the sealed DS1 iteration-24 TRAIN-only rate cross-fit audit."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
I23_DIR = ROOT / "reports/2026_09_25_ds1_iteration23_widened_rate"
I23_RUN = I23_DIR / "run.py"
I23_ARTIFACT = I23_DIR / "smoke.json"
RATE_BOUND_S_H = 1.0
RATE_SIGMA_S_H = 0.09176615913014215
RATE_RANGE_GATE_S_H = 0.1835323183
ROBUST_SCALE_HZ = 250.0
EXACT_REPLAY_TOLERANCE_HZ = 0.2
MINIMUM_TRACKS = 3
MINIMUM_TOTAL_ROWS = 24
MINIMUM_FOLD_TRACKS = 2
MINIMUM_FOLD_ROWS = 24
COMPUTE_LIMIT_S = 600.0
REQUIRED_SPARSE_SOURCES = ("57248", "58683")


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


def verified_json(path: Path) -> dict[str, Any]:
    seal = path.with_suffix(path.suffix + ".sha256")
    expected = seal.read_text().strip().split()[0]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"seal mismatch: {path}")
    return json.loads(path.read_text())


def load_sources() -> tuple[Any, dict[str, Any], dict[str, Any]]:
    plan = verified_json(PLAN)
    if (
        plan.get("status") != "sealed-fixed-coordinate-train-only-crossfit-rate-audit"
        or plan.get("reference_used_for_inference") is not False
        or float(plan.get("compute_limit_s", -1)) != COMPUTE_LIMIT_S
    ):
        raise ValueError("plan does not authorize this audit")
    artifact = verified_json(I23_ARTIFACT)
    if (
        artifact.get("schema") != "ds1-iteration23-widened-rate-audit/v1"
        or artifact.get("complete") is not True
        or artifact.get("reference_used") is not False
        or artifact.get("held_used_for_selection") is not False
        or artifact.get("geographic_search_run") is not False
    ):
        raise ValueError("iteration23 source artifact is not finalized TRAIN-only evidence")
    if artifact.get("bindings", {}).get("runner") != digest(I23_RUN):
        raise ValueError("iteration23 artifact is not bound to the available iteration23 code")
    i23 = load_module(I23_RUN, "ds1_iteration23_finalized")
    return i23, artifact, plan


def support_record(data: Any, source: str) -> dict[str, Any]:
    train = np.asarray(data.train, dtype=bool)
    sources = data.source.astype(str)
    tracks = data.track.astype(str)
    rows = np.flatnonzero(train & (sources == source))
    names = tuple(sorted(str(value) for value in np.unique(tracks[rows])))
    counts = {track: int(np.sum(tracks[rows] == track)) for track in names}
    remaining = {track: int(len(rows) - counts[track]) for track in names}
    reasons = []
    if len(names) < MINIMUM_TRACKS:
        reasons.append("fewer_than_3_training_tracks")
    if len(rows) < MINIMUM_TOTAL_ROWS:
        reasons.append("fewer_than_24_total_training_rows")
    if names and any(len(names) - 1 < MINIMUM_FOLD_TRACKS for _track in names):
        reasons.append("a_fold_leaves_fewer_than_2_training_tracks")
    if names and any(value < MINIMUM_FOLD_ROWS for value in remaining.values()):
        reasons.append("a_fold_leaves_fewer_than_24_training_rows")
    return {
        "training_observations": int(len(rows)),
        "training_tracks": len(names),
        "track_training_observations": counts,
        "fold_remaining_training_observations": remaining,
        "eligible": not reasons,
        "ineligibility_reasons": reasons,
    }


def make_objectives(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    rows: np.ndarray,
) -> tuple[Callable[[float], float], Callable[[np.ndarray], np.ndarray]]:
    """Build the iteration23 robust TRAIN objective for an explicit row set."""
    rows = np.asarray(rows, dtype=int)
    observations = np.asarray(data.y[rows], dtype=float)
    ages = np.asarray(data.age_h[rows], dtype=float)
    position_nodes = np.asarray(data.p_nodes[rows], dtype=float)
    velocity_nodes = np.asarray(data.v_nodes[rows], dtype=float)
    observation_tracks = data.track[rows].astype(str)
    tracks = tuple(sorted(str(value) for value in np.unique(observation_tracks)))

    def objective(rate: float) -> float:
        phase = ages * float(rate)
        prediction = orbit.doppler(
            receiver,
            orbit.quartic(position_nodes, phase),
            orbit.quartic(velocity_nodes, phase),
            search,
        )
        raw = observations - prediction
        total = 0.0
        for track in tracks:
            selected = observation_tracks == track
            error = raw[selected] - np.mean(raw[selected])
            z = error / ROBUST_SCALE_HZ
            total += float(np.sum(np.sqrt(1.0 + z * z) - 1.0))
        return total + 0.5 * (float(rate) / RATE_SIGMA_S_H) ** 2

    def objective_many(rates: np.ndarray) -> np.ndarray:
        values = np.asarray(rates, dtype=float)
        answers = np.empty(len(values), dtype=float)
        for start in range(0, len(values), 128):
            selected_rates = values[start : start + 128]
            count = len(selected_rates)
            phase = (selected_rates[:, None] * ages[None, :]).reshape(-1)
            prediction = orbit.doppler(
                receiver,
                orbit.quartic(np.tile(position_nodes, (count, 1, 1)), phase),
                orbit.quartic(np.tile(velocity_nodes, (count, 1, 1)), phase),
                search,
            ).reshape(count, len(observations))
            raw = observations[None, :] - prediction
            total = np.zeros(count, dtype=float)
            for track in tracks:
                selected = observation_tracks == track
                error = raw[:, selected] - np.mean(raw[:, selected], axis=1)[:, None]
                z = error / ROBUST_SCALE_HZ
                total += np.sum(np.sqrt(1.0 + z * z) - 1.0, axis=1)
            answers[start : start + count] = total + 0.5 * (selected_rates / RATE_SIGMA_S_H) ** 2
        return answers

    return objective, objective_many


def omitted_track_score(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    rows: np.ndarray,
    rate_s_h: float,
) -> dict[str, Any]:
    """Fit exactly one omitted-track CFO and return observation loss only."""
    phase = np.asarray(data.age_h[rows], dtype=float) * float(rate_s_h)
    prediction = orbit.doppler(
        receiver,
        orbit.quartic(data.p_nodes[rows], phase),
        orbit.quartic(data.v_nodes[rows], phase),
        search,
    )
    raw = np.asarray(data.y[rows], dtype=float) - prediction
    cfo = float(np.mean(raw))
    error = raw - cfo
    z = error / ROBUST_SCALE_HZ
    loss = float(np.sum(np.sqrt(1.0 + z * z) - 1.0))
    return {
        "observations": int(len(rows)),
        "fitted_cfo_hz": cfo,
        "robust_loss": loss,
        "robust_loss_per_observation": loss / len(rows),
        "rms_hz": float(np.sqrt(np.mean(error * error))),
    }


def exact_replay(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    replay: Any,
    catalogues: dict[str, Any],
    tau_s: float,
    source: str,
    rows: np.ndarray,
    rate_s_h: float,
) -> dict[str, Any]:
    """Replay a fold winner with exact SGP4 on its remaining TRAIN rows."""
    errors = []
    phases = []
    session_values = data.session.astype(str)
    for sid in sorted(str(value) for value in np.unique(session_values[rows])):
        local = rows[session_values[rows] == sid]
        info = data.sources[sid]
        catalogue = catalogues[info["snapshot_digest"]]
        index = {str(number): i for i, number in enumerate(catalogue.satellite_numbers)}
        phase_s = float(data.age_h[local[0]] * rate_s_h)
        if np.max(np.abs(np.asarray(data.age_h[local], float) * rate_s_h - phase_s)) > 1e-12:
            raise ValueError("source/session causal phase is not constant")
        p, v, valid = replay.state_arrays(
            catalogue,
            [index[source]],
            int(info["capture_start_utc_ns"]),
            data.time_s[local],
            orbit_time_s=phase_s,
            clock_s=float(tau_s),
        )
        if len(valid) != 1:
            raise ValueError("exact fold propagation failed")
        exact = orbit.doppler(receiver, p[0], v[0], search)
        approximate = orbit.doppler(
            receiver,
            orbit.quartic(data.p_nodes[local], np.full(len(local), phase_s)),
            orbit.quartic(data.v_nodes[local], np.full(len(local), phase_s)),
            search,
        )
        errors.append(np.asarray(approximate - exact, dtype=float))
        phases.append(phase_s)
    error = np.concatenate(errors)
    maximum = float(np.max(np.abs(error)))
    return {
        "schema": "ds1-iteration24-fold-exact-sgp4-replay/v1",
        "training_observations": int(len(error)),
        "tolerance_hz": EXACT_REPLAY_TOLERANCE_HZ,
        "rms_hz": float(np.sqrt(np.mean(error * error))),
        "maximum_absolute_hz": maximum,
        "maximum_absolute_phase_s": float(np.max(np.abs(phases))),
        "passed": maximum <= EXACT_REPLAY_TOLERANCE_HZ,
        "earth_rotation": "fixed at receive_time_plus_global_tau",
    }


def sign_basin(rate_s_h: float) -> str:
    if rate_s_h < 0:
        return "negative"
    if rate_s_h > 0:
        return "positive"
    return "zero"


def negative_basin_audit(profile: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        {
            "rate_s_h": float(row["rate_s_h"]),
            "training_objective": float(row["objective"]),
            "kind": "refined_local_minimum",
        }
        for row in profile["refinements"]
        if float(row["rate_s_h"]) < 0
    ]
    candidates.append(
        {
            "rate_s_h": -RATE_BOUND_S_H,
            "training_objective": float("nan"),
            "kind": "endpoint_not_retained_by_iteration23_profile_record",
        }
    )
    finite = [row for row in candidates if np.isfinite(row["training_objective"])]
    best = min(finite, key=lambda row: row["training_objective"]) if finite else None
    return {
        "negative_refined_local_minimum_count": len(finite),
        "best_negative_refined_candidate": best,
        "negative_basin_won": sign_basin(float(profile["rate_s_h"])) == "negative",
    }


def run_source(
    data: Any,
    receiver: np.ndarray,
    search: Any,
    orbit: Any,
    replay: Any,
    catalogues: dict[str, Any],
    tau_s: float,
    source: str,
    full_rate_s_h: float,
    i23: Any,
    deadline: float,
) -> dict[str, Any]:
    support = support_record(data, source)
    base = {
        "source": source,
        "support": support,
        "iteration23_full_training_diagnostic_rate_s_h": float(full_rate_s_h),
        "prospective_rate_s_h": float(full_rate_s_h) if support["eligible"] else 0.0,
    }
    if not support["eligible"]:
        return {
            **base,
            "folds": [],
            "gate": {
                "applicable": False,
                "passed": None,
                "reason": "predeclared support ineligible; prospective rate forced to zero",
            },
        }

    train = np.asarray(data.train, dtype=bool)
    sources = data.source.astype(str)
    tracks = data.track.astype(str)
    source_rows = np.flatnonzero(train & (sources == source))
    source_tracks = tuple(sorted(str(value) for value in np.unique(tracks[source_rows])))
    folds = []
    boundary_tolerance = float(i23.boundary_tolerance_s_h(RATE_BOUND_S_H))
    for omitted_track in source_tracks:
        if time.perf_counter() >= deadline:
            raise TimeoutError("predeclared 600-second compute limit reached")
        omitted_rows = source_rows[tracks[source_rows] == omitted_track]
        fitting_rows = source_rows[tracks[source_rows] != omitted_track]
        objective, objective_many = make_objectives(data, receiver, search, orbit, fitting_rows)
        profile = i23.global_profile_minimize(
            objective,
            RATE_BOUND_S_H,
            maximum_abs_age_h=float(np.max(np.abs(data.age_h[fitting_rows]))),
            objective_many=objective_many,
        )
        rate = float(profile["rate_s_h"])
        replay_result = exact_replay(
            data,
            receiver,
            search,
            orbit,
            replay,
            catalogues,
            tau_s,
            source,
            fitting_rows,
            rate,
        )
        fitted_score = omitted_track_score(data, receiver, search, orbit, omitted_rows, rate)
        zero_score = omitted_track_score(data, receiver, search, orbit, omitted_rows, 0.0)
        folds.append(
            {
                "omitted_track_id": omitted_track,
                "fitting_training_tracks": len(source_tracks) - 1,
                "fitting_training_observations": int(len(fitting_rows)),
                "omitted_training_observations": int(len(omitted_rows)),
                "profile": profile,
                "winning_sign_basin": sign_basin(rate),
                "negative_basin_audit": negative_basin_audit(profile),
                "exact_sgp4_replay": replay_result,
                "omitted_track_fitted_rate_score": fitted_score,
                "omitted_track_zero_rate_score": zero_score,
                "omitted_track_robust_loss_improvement": (
                    zero_score["robust_loss"] - fitted_score["robust_loss"]
                ),
            }
        )
    rates = [float(row["profile"]["rate_s_h"]) for row in folds]
    basins = [row["winning_sign_basin"] for row in folds]
    candidate_loss = float(
        sum(row["omitted_track_fitted_rate_score"]["robust_loss"] for row in folds)
    )
    zero_loss = float(sum(row["omitted_track_zero_rate_score"]["robust_loss"] for row in folds))
    criteria = {
        "all_fold_profiles_converged": all(row["profile"]["converged"] for row in folds),
        "all_fold_exact_sgp4_replays_passed": all(
            row["exact_sgp4_replay"]["passed"] for row in folds
        ),
        "all_fold_winners_interior": all(
            RATE_BOUND_S_H - abs(rate) > boundary_tolerance for rate in rates
        ),
        "same_nonzero_winning_sign_basin": len(set(basins)) == 1 and basins[0] != "zero",
        "fold_rate_range_within_2sigma": max(rates) - min(rates) <= RATE_RANGE_GATE_S_H,
        "aggregate_omitted_track_robust_score_improves_zero": candidate_loss < zero_loss,
    }
    return {
        **base,
        "folds": folds,
        "aggregate_omitted_track_score": {
            "observations": int(sum(row["omitted_training_observations"] for row in folds)),
            "fitted_rate_robust_loss": candidate_loss,
            "zero_rate_robust_loss": zero_loss,
            "fitted_minus_zero_robust_loss": candidate_loss - zero_loss,
            "improves_zero": candidate_loss < zero_loss,
        },
        "fold_rate_summary": {
            "minimum_s_h": min(rates),
            "maximum_s_h": max(rates),
            "range_s_h": max(rates) - min(rates),
            "range_gate_s_h": RATE_RANGE_GATE_S_H,
            "winning_sign_basins": basins,
            "unique_winning_sign_basins": sorted(set(basins)),
            "negative_basin_win_count": basins.count("negative"),
        },
        "gate": {
            "applicable": True,
            "criteria": criteria,
            "passed": all(criteria.values()),
        },
    }


def run_group(
    i23: Any,
    source_group: dict[str, Any],
    deadline: float,
) -> dict[str, Any]:
    group = str(source_group["group_id"])
    ds1 = i23.load_module(i23.DS1_RUNNER, f"i24_ds1_{group}")
    orbit = i23.load_module(i23.ORBIT, f"i24_orbit_{group}")
    replay = load_module(ROOT / "tools/replay_regional_doppler.py", f"i24_replay_{group}")
    from leo.sky.propagation import parse_element_sets

    case = i23.load_case(group)
    point = {
        key: float(source_group["fixed_point"][key])
        for key in ("latitude_deg", "longitude_deg", "tau_s")
    }
    _clock, engine = ds1.make_engine(case)
    for session in engine.sessions:
        session["cache_path"] = str(ds1.CACHE_ROOTS[group] / session["session_id"])
    data = orbit.prepare(engine, point["latitude_deg"], point["longitude_deg"], point["tau_s"])
    receiver, _up = engine.search.receiver_ecef(point["latitude_deg"], point["longitude_deg"])
    payloads = {
        info["snapshot_digest"]: orbit.archive_payload(info["snapshot_digest"])
        for info in data.sources.values()
    }
    catalogues = {key: parse_element_sets(value.decode("ascii")) for key, value in payloads.items()}
    diagnostic = source_group["rate_schedule"][2]
    if float(diagnostic["rate_bound_s_h"]) != RATE_BOUND_S_H:
        raise ValueError("iteration23 diagnostic rate arm is not +/-1 s/hour")
    full_rates = {str(key): float(value) for key, value in diagnostic["fit"]["rates_s_h"].items()}
    train_sources = tuple(
        sorted(str(value) for value in np.unique(data.source[data.train].astype(str)))
    )
    if set(full_rates) != set(train_sources):
        raise ValueError("iteration23 diagnostic source membership mismatch")
    sources = [
        run_source(
            data,
            receiver,
            engine.search,
            orbit,
            replay,
            catalogues,
            point["tau_s"],
            source,
            full_rates[source],
            i23,
            deadline,
        )
        for source in train_sources
    ]
    eligible = [row for row in sources if row["support"]["eligible"]]
    ineligible = [row for row in sources if not row["support"]["eligible"]]
    return {
        "group_id": group,
        "case_id": case["case_id"],
        "fixed_point": point,
        "training_observations": int(np.sum(data.train)),
        "held_observations_not_read_or_scored": int(np.sum(~data.train)),
        "sources": sources,
        "support_coverage": {
            "source_count": len(sources),
            "eligible_source_count": len(eligible),
            "ineligible_source_count": len(ineligible),
            "eligible_fold_count": sum(len(row["folds"]) for row in eligible),
            "eligible_source_gate_pass_count": sum(row["gate"]["passed"] for row in eligible),
            "eligible_source_gate_fail_count": sum(not row["gate"]["passed"] for row in eligible),
            "ineligible_sources": [row["source"] for row in ineligible],
        },
        "prospective_rates_s_h": {row["source"]: row["prospective_rate_s_h"] for row in sources},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    begun = time.perf_counter()
    deadline = begun + COMPUTE_LIMIT_S
    i23, source_artifact, _plan = load_sources()
    groups = [run_group(i23, group, deadline) for group in source_artifact["groups"]]
    all_sources = [row for group in groups for row in group["sources"]]
    eligible = [row for row in all_sources if row["support"]["eligible"]]
    sparse = {row["source"]: row for row in all_sources if row["source"] in REQUIRED_SPARSE_SOURCES}
    if set(sparse) != set(REQUIRED_SPARSE_SOURCES):
        raise ValueError("required sparse source is absent")
    if any(
        row["support"]["eligible"] or row["prospective_rate_s_h"] != 0 for row in sparse.values()
    ):
        raise ValueError("required sparse source was not forced ineligible/zero")
    source_68739 = next(row for row in all_sources if row["source"] == "68739")
    if len(source_68739["folds"]) != 5:
        raise ValueError("NORAD 68739 did not produce exactly five folds")
    elapsed = time.perf_counter() - begun
    if elapsed > COMPUTE_LIMIT_S:
        raise TimeoutError("predeclared compute limit exceeded")
    go = all(row["gate"]["passed"] for row in eligible)
    output = {
        "schema": "ds1-iteration24-crossfit-rate-audit/v1",
        "complete": True,
        "reference_used": False,
        "held_used_for_fit_score_gate_or_decision": False,
        "geographic_search_run": False,
        "groups": groups,
        "explicit_audits": {
            "68739": source_68739,
            "57248": sparse["57248"],
            "58683": sparse["58683"],
        },
        "summary": {
            "source_count": len(all_sources),
            "eligible_source_count": len(eligible),
            "ineligible_source_count": len(all_sources) - len(eligible),
            "fold_count": sum(len(row["folds"]) for row in eligible),
            "eligible_source_gate_pass_count": sum(row["gate"]["passed"] for row in eligible),
            "eligible_source_gate_fail_count": sum(not row["gate"]["passed"] for row in eligible),
            "all_eligible_sources_passed": go,
            "prospective_fixed_coordinate_rate_model": {
                "decision": "go" if go else "no-go",
                "scope": "a subsequent separately sealed fixed-coordinate evaluation only",
                "ineligible_source_rate_s_h": 0.0,
                "held_used_for_decision": False,
            },
            "geographic_basin": {
                "decision": "not-authorized",
                "launched": False,
            },
            "compute_limit_s": COMPUTE_LIMIT_S,
            "elapsed_s": elapsed,
        },
        "bindings": {
            "plan": digest(PLAN),
            "runner": digest(Path(__file__)),
            "iteration23_runner": digest(I23_RUN),
            "iteration23_artifact": digest(I23_ARTIFACT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(json.dumps({"output": str(args.output), "summary": output["summary"]}, sort_keys=True))


if __name__ == "__main__":
    main()
