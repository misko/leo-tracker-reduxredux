#!/usr/bin/env python3
"""Run the sealed DS1 iteration-25 fixed-coordinate source-admission evaluation."""

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

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
PLAN = HERE / "plan.json"
I23_DIR = ROOT / "reports/2026_09_25_ds1_iteration23_widened_rate"
I23_RUN = I23_DIR / "run.py"
I23_ARTIFACT = I23_DIR / "smoke.json"
I24_DIR = ROOT / "reports/2026_09_25_ds1_iteration24_crossfit_rate"
I24_RUN = I24_DIR / "run.py"
I24_ARTIFACT = I24_DIR / "audit.json"
CAP_HZ = 800.0
EXACT_REPLAY_TOLERANCE_HZ = 0.2
SESSION_REGRESSION_LIMIT = 0.05
REQUIRED_ADMITTED_SOURCES = 65
REQUIRED_ZERO_SOURCES = 186
REQUIRED_TOTAL_SOURCES = 251
COMPUTE_LIMIT_S = 300.0


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


def load_sources() -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = verified_json(PLAN)
    if (
        plan.get("status") != "sealed-fixed-coordinate-source-admission-held-evaluation"
        or plan.get("truth_used") is not False
        or plan.get("geographic_search_run") is not False
        or float(plan.get("compute_limit_s", -1)) != COMPUTE_LIMIT_S
    ):
        raise ValueError("plan does not authorize this evaluation")
    i24 = verified_json(I24_ARTIFACT)
    if (
        i24.get("schema") != "ds1-iteration24-crossfit-rate-audit/v1"
        or i24.get("complete") is not True
        or i24.get("reference_used") is not False
        or i24.get("held_used_for_fit_score_gate_or_decision") is not False
        or i24.get("geographic_search_run") is not False
    ):
        raise ValueError("iteration24 artifact is not finalized TRAIN-only evidence")
    if i24.get("bindings", {}).get("runner") != digest(I24_RUN):
        raise ValueError("iteration24 artifact is not bound to the available code")
    i23 = verified_json(I23_ARTIFACT)
    if (
        i23.get("schema") != "ds1-iteration23-widened-rate-audit/v1"
        or i23.get("complete") is not True
        or i23.get("reference_used") is not False
        or i23.get("held_used_for_selection") is not False
        or i23.get("geographic_search_run") is not False
    ):
        raise ValueError("iteration23 artifact is not finalized fixed-coordinate evidence")
    if i23.get("bindings", {}).get("runner") != digest(I23_RUN):
        raise ValueError("iteration23 artifact is not bound to the available code")
    if i24.get("bindings", {}).get("iteration23_artifact") != digest(I23_ARTIFACT):
        raise ValueError("iteration24 and iteration23 artifacts are not bound")
    return load_module(I23_RUN, "ds1_iteration23_for_iteration25"), i23, i24, plan


def controls(source_group: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_bound = {float(row["rate_bound_s_h"]): row for row in source_group["rate_schedule"]}
    if set(by_bound) != {0.25, 0.5, 1.0}:
        raise ValueError("unexpected iteration23 rate schedule")
    return {
        "zero_rate": source_group["zero_rate"]["score"],
        "all_source_bound_0.25_s_h": by_bound[0.25]["score"],
        "all_source_bound_1_s_h": by_bound[1.0]["score"],
    }


def frozen_rates(
    crossfit_group: dict[str, Any],
    source_group: dict[str, Any],
) -> tuple[dict[str, float], list[str], list[str]]:
    diagnostic = next(
        row for row in source_group["rate_schedule"] if float(row["rate_bound_s_h"]) == 1.0
    )
    full_train = {
        str(source): float(rate) for source, rate in diagnostic["fit"]["rates_s_h"].items()
    }
    source_rows = {str(row["source"]): row for row in crossfit_group["sources"]}
    if set(source_rows) != set(full_train):
        raise ValueError("iteration23/24 source membership mismatch")
    enabled = sorted(
        source
        for source, row in source_rows.items()
        if row["support"]["eligible"] and row["gate"]["passed"] is True
    )
    zeroed = sorted(set(source_rows) - set(enabled))
    rates = {source: full_train[source] if source in enabled else 0.0 for source in source_rows}
    for source, row in source_rows.items():
        expected = float(row["iteration23_full_training_diagnostic_rate_s_h"])
        if full_train[source] != expected:
            raise ValueError(f"iteration24 rate binding mismatch: {source}")
        if source in zeroed and rates[source] != 0.0:
            raise ValueError(f"non-admitted source is not exactly zero: {source}")
    return rates, enabled, zeroed


def session_changes(
    candidate: dict[str, Any], comparator_scores: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    by_control = {
        name: {str(row["session_id"]): row for row in score["session_scores"]}
        for name, score in comparator_scores.items()
    }
    candidate_ids = {str(row["session_id"]) for row in candidate["session_scores"]}
    if any(set(rows) != candidate_ids for rows in by_control.values()):
        raise ValueError("comparator session membership mismatch")
    result = []
    for row in candidate["session_scores"]:
        sid = str(row["session_id"])
        item: dict[str, Any] = {
            "session_id": sid,
            "candidate_training_capped_loss": float(row["training_capped_loss"]),
            "candidate_held_capped_loss": float(row["held_capped_loss"]),
        }
        for name, sessions in by_control.items():
            control = sessions[sid]
            item[f"{name}_training_capped_loss"] = float(control["training_capped_loss"])
            item[f"candidate_minus_{name}_training"] = float(
                row["training_capped_loss"] - control["training_capped_loss"]
            )
            item[f"{name}_held_capped_loss"] = float(control["held_capped_loss"])
            item[f"candidate_minus_{name}_held"] = float(
                row["held_capped_loss"] - control["held_capped_loss"]
            )
        result.append(item)
    return result


def enabled_support(score: dict[str, Any], enabled: list[str]) -> dict[str, Any]:
    selected = [row for row in score["track_scores"] if str(row["source"]) in set(enabled)]
    by_session = []
    for session in score["session_scores"]:
        sid = str(session["session_id"])
        rows = [row for row in selected if str(row["session_id"]) == sid]
        by_session.append(
            {
                "session_id": sid,
                "enabled_source_count": len({str(row["source"]) for row in rows}),
                "enabled_track_count": len(rows),
                "training_observations": int(sum(row["train_observations"] for row in rows)),
                "held_observations": int(sum(row["held_observations"] for row in rows)),
                "occupied_second_weight": float(sum(row["occupied_second_weight"] for row in rows)),
            }
        )
    return {
        "enabled_source_count": len(enabled),
        "enabled_sources": enabled,
        "enabled_track_count": len(selected),
        "training_observations": int(sum(row["train_observations"] for row in selected)),
        "held_observations": int(sum(row["held_observations"] for row in selected)),
        "occupied_second_weight": float(sum(row["occupied_second_weight"] for row in selected)),
        "by_session": by_session,
    }


def capped_track_loss(rms_hz: float) -> float:
    return float(min((float(rms_hz) / CAP_HZ) ** 2, 1.0))


def source_zero_sensitivity(
    candidate: dict[str, Any], zero: dict[str, Any], source: str
) -> dict[str, Any]:
    candidate_tracks = {
        str(row["track_id"]): row
        for row in candidate["track_scores"]
        if str(row["source"]) == source
    }
    zero_tracks = {
        str(row["track_id"]): row for row in zero["track_scores"] if str(row["source"]) == source
    }
    if set(candidate_tracks) != set(zero_tracks) or not candidate_tracks:
        raise ValueError(f"source sensitivity track mismatch or absence: {source}")
    session_results = []
    for session in candidate["session_scores"]:
        sid = str(session["session_id"])
        denominator = float(session["occupied_second_weight"])
        rows = [row for row in candidate_tracks.values() if str(row["session_id"]) == sid]
        training_delta_numerator = 0.0
        held_delta_numerator = 0.0
        track_results = []
        for row in rows:
            baseline = zero_tracks[str(row["track_id"])]
            weight = float(row["occupied_second_weight"])
            if float(baseline["occupied_second_weight"]) != weight:
                raise ValueError("source sensitivity track weight mismatch")
            train_delta = weight * (
                capped_track_loss(baseline["training_rms_hz"])
                - capped_track_loss(row["training_rms_hz"])
            )
            held_delta = weight * (
                capped_track_loss(baseline["held_rms_hz"]) - capped_track_loss(row["held_rms_hz"])
            )
            training_delta_numerator += train_delta
            held_delta_numerator += held_delta
            track_results.append(
                {
                    "track_id": str(row["track_id"]),
                    "training_observations": int(row["train_observations"]),
                    "held_observations": int(row["held_observations"]),
                    "occupied_second_weight": weight,
                    "candidate_training_rms_hz": float(row["training_rms_hz"]),
                    "zero_rate_training_rms_hz": float(baseline["training_rms_hz"]),
                    "candidate_held_rms_hz": float(row["held_rms_hz"]),
                    "zero_rate_held_rms_hz": float(baseline["held_rms_hz"]),
                    "zeroed_minus_candidate_training_numerator": train_delta,
                    "zeroed_minus_candidate_held_numerator": held_delta,
                }
            )
        zeroed_training = (
            float(session["training_capped_loss"]) + training_delta_numerator / denominator
        )
        zeroed_held = float(session["held_capped_loss"]) + held_delta_numerator / denominator
        session_results.append(
            {
                "session_id": sid,
                "source_track_count": len(rows),
                "source_training_observations": int(sum(row["train_observations"] for row in rows)),
                "source_held_observations": int(sum(row["held_observations"] for row in rows)),
                "source_occupied_second_weight": float(
                    sum(row["occupied_second_weight"] for row in rows)
                ),
                "candidate_training_capped_loss": float(session["training_capped_loss"]),
                "source_zeroed_training_capped_loss": zeroed_training,
                "candidate_minus_source_zeroed_training": float(
                    session["training_capped_loss"] - zeroed_training
                ),
                "candidate_held_capped_loss": float(session["held_capped_loss"]),
                "source_zeroed_held_capped_loss": zeroed_held,
                "candidate_minus_source_zeroed_held": float(
                    session["held_capped_loss"] - zeroed_held
                ),
                "tracks": track_results,
            }
        )
    return {
        "source": source,
        "method": (
            "exact separable reconstruction from candidate and sealed zero-rate track scores; "
            "no additional HELD model score"
        ),
        "track_count": len(candidate_tracks),
        "training_observations": int(
            sum(row["train_observations"] for row in candidate_tracks.values())
        ),
        "held_observations": int(
            sum(row["held_observations"] for row in candidate_tracks.values())
        ),
        "occupied_second_weight": float(
            sum(row["occupied_second_weight"] for row in candidate_tracks.values())
        ),
        "candidate_training_capped_loss": float(candidate["equal_session_training_capped_loss"]),
        "source_zeroed_training_capped_loss": float(
            np.mean([row["source_zeroed_training_capped_loss"] for row in session_results])
        ),
        "candidate_held_capped_loss": float(candidate["equal_session_held_capped_loss"]),
        "source_zeroed_held_capped_loss": float(
            np.mean([row["source_zeroed_held_capped_loss"] for row in session_results])
        ),
        "candidate_minus_source_zeroed_held": float(
            candidate["equal_session_held_capped_loss"]
            - np.mean([row["source_zeroed_held_capped_loss"] for row in session_results])
        ),
        "sessions": session_results,
    }


def run_group(
    i23: Any,
    source_group: dict[str, Any],
    crossfit_group: dict[str, Any],
) -> dict[str, Any]:
    group = str(source_group["group_id"])
    if str(crossfit_group["group_id"]) != group:
        raise ValueError("iteration23/24 group mismatch")
    if source_group["fixed_point"] != crossfit_group["fixed_point"]:
        raise ValueError("iteration23/24 fixed point mismatch")
    rates, enabled, zeroed = frozen_rates(crossfit_group, source_group)
    ds1 = i23.load_module(i23.DS1_RUNNER, f"i25_ds1_{group}")
    orbit = i23.load_module(i23.ORBIT, f"i25_orbit_{group}")
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
    if set(rates) != set(np.unique(data.source.astype(str))):
        raise ValueError("candidate/data source membership mismatch")
    unsupported = i23.unsupported_by_session(engine, data.assignments)

    # The only new candidate HELD score. Membership, coordinates, tau, and all
    # rates were frozen above from sealed TRAIN-only evidence.
    score = i23.score_rates(data, receiver, engine.search, orbit, rates, unsupported)
    replay = orbit.exact_replay_gate(
        data, receiver, engine.search, point["tau_s"], rates, tolerance_hz=EXACT_REPLAY_TOLERANCE_HZ
    )
    comparator_scores = controls(source_group)
    changes = session_changes(score, comparator_scores)
    support = enabled_support(score, enabled)
    sensitivity = (
        source_zero_sensitivity(score, comparator_scores["zero_rate"], "68739")
        if "68739" in enabled
        else None
    )
    comparisons = {
        name: {
            "training_capped_loss": float(control["equal_session_training_capped_loss"]),
            "held_capped_loss": float(control["equal_session_held_capped_loss"]),
            "candidate_minus_control_training": float(
                score["equal_session_training_capped_loss"]
                - control["equal_session_training_capped_loss"]
            ),
            "candidate_minus_control_held": float(
                score["equal_session_held_capped_loss"] - control["equal_session_held_capped_loss"]
            ),
        }
        for name, control in comparator_scores.items()
    }
    group_gate = {
        "exact_replay_passed": bool(replay["passed"]),
        "candidate_below_every_control_held": all(
            row["candidate_minus_control_held"] < 0 for row in comparisons.values()
        ),
        "at_least_four_sessions_improve_zero": sum(
            row["candidate_minus_zero_rate_held"] < 0 for row in changes
        )
        >= 4,
        "no_session_regression_over_0.05": max(
            row["candidate_minus_zero_rate_held"] for row in changes
        )
        <= SESSION_REGRESSION_LIMIT,
    }
    return {
        "group_id": group,
        "case_id": case["case_id"],
        "fixed_point": point,
        "held_score_call_count": 1,
        "source_policy": {
            "group_source_count": len(rates),
            "enabled_source_count": len(enabled),
            "zero_source_count": len(zeroed),
            "enabled_sources": enabled,
            "zero_sources": zeroed,
            "rates_s_h": rates,
        },
        "support": support,
        "candidate_score": score,
        "comparisons": comparisons,
        "per_session_changes": changes,
        "exact_sgp4_replay": replay,
        "source_68739_sensitivity": sensitivity,
        "gate": {"criteria": group_gate, "passed": all(group_gate.values())},
    }


def pooled_scores(groups: list[dict[str, Any]]) -> dict[str, Any]:
    session_count = sum(len(group["candidate_score"]["session_scores"]) for group in groups)
    if session_count != 12:
        raise ValueError("expected twelve equal-weight sessions")
    candidate_train = float(
        np.mean(
            [
                row["candidate_training_capped_loss"]
                for group in groups
                for row in group["per_session_changes"]
            ]
        )
    )
    candidate_held = float(
        np.mean(
            [
                row["candidate_held_capped_loss"]
                for group in groups
                for row in group["per_session_changes"]
            ]
        )
    )
    names = tuple(groups[0]["comparisons"])
    comparisons = {}
    for name in names:
        control_train = float(
            np.mean(
                [
                    row[f"{name}_training_capped_loss"]
                    for group in groups
                    for row in group["per_session_changes"]
                ]
            )
        )
        control_held = float(
            np.mean(
                [
                    row[f"{name}_held_capped_loss"]
                    for group in groups
                    for row in group["per_session_changes"]
                ]
            )
        )
        comparisons[name] = {
            "training_capped_loss": control_train,
            "held_capped_loss": control_held,
            "candidate_minus_control_training": candidate_train - control_train,
            "candidate_minus_control_held": candidate_held - control_held,
        }
    return {
        "session_count": session_count,
        "candidate_training_capped_loss": candidate_train,
        "candidate_held_capped_loss": candidate_held,
        "comparisons": comparisons,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("output exists")
    begun = time.perf_counter()
    i23_runner, source_artifact, crossfit_artifact, _plan = load_sources()
    source_groups = {str(row["group_id"]): row for row in source_artifact["groups"]}
    crossfit_groups = {str(row["group_id"]): row for row in crossfit_artifact["groups"]}
    if set(source_groups) != set(crossfit_groups):
        raise ValueError("iteration23/24 group membership mismatch")
    groups = [
        run_group(i23_runner, source_groups[group], crossfit_groups[group])
        for group in sorted(source_groups)
    ]
    enabled_count = sum(group["source_policy"]["enabled_source_count"] for group in groups)
    zero_count = sum(group["source_policy"]["zero_source_count"] for group in groups)
    total_count = sum(group["source_policy"]["group_source_count"] for group in groups)
    if (enabled_count, zero_count, total_count) != (
        REQUIRED_ADMITTED_SOURCES,
        REQUIRED_ZERO_SOURCES,
        REQUIRED_TOTAL_SOURCES,
    ):
        raise ValueError("predeclared source counts do not match")
    pooled = pooled_scores(groups)
    pooled_superiority = all(
        row["candidate_minus_control_held"] < 0 for row in pooled["comparisons"].values()
    )
    criteria = {
        "all_group_exact_replays_passed": all(
            group["gate"]["criteria"]["exact_replay_passed"] for group in groups
        ),
        "candidate_below_every_control_in_each_group": all(
            group["gate"]["criteria"]["candidate_below_every_control_held"] for group in groups
        ),
        "candidate_below_every_control_pooled": pooled_superiority,
        "at_least_four_sessions_improve_zero_in_each_group": all(
            group["gate"]["criteria"]["at_least_four_sessions_improve_zero"] for group in groups
        ),
        "no_session_regression_over_0.05": all(
            group["gate"]["criteria"]["no_session_regression_over_0.05"] for group in groups
        ),
    }
    passed = all(criteria.values())
    elapsed = time.perf_counter() - begun
    if elapsed > COMPUTE_LIMIT_S:
        raise TimeoutError("predeclared compute limit exceeded")
    output = {
        "schema": "ds1-iteration25-source-admission-evaluation/v1",
        "complete": True,
        "reference_used": False,
        "truth_used": False,
        "held_used_for_model_choice": False,
        "candidate_held_score_calls_per_group": 1,
        "geographic_search_run": False,
        "groups": groups,
        "pooled_equal_session_scores": pooled,
        "gate": {
            "criteria": criteria,
            "passed": passed,
            "prospective_geographic_basin_design": "justified" if passed else "not-justified",
            "geographic_basin_run_authorized": False,
        },
        "summary": {
            "group_source_count": total_count,
            "enabled_source_count": enabled_count,
            "zero_source_count": zero_count,
            "enabled_track_count": sum(group["support"]["enabled_track_count"] for group in groups),
            "enabled_training_observations": sum(
                group["support"]["training_observations"] for group in groups
            ),
            "enabled_held_observations": sum(
                group["support"]["held_observations"] for group in groups
            ),
            "enabled_occupied_second_weight": sum(
                group["support"]["occupied_second_weight"] for group in groups
            ),
            "compute_limit_s": COMPUTE_LIMIT_S,
            "elapsed_s": elapsed,
        },
        "bindings": {
            "plan": digest(PLAN),
            "runner": digest(Path(__file__)),
            "iteration23_runner": digest(I23_RUN),
            "iteration23_artifact": digest(I23_ARTIFACT),
            "iteration24_runner": digest(I24_RUN),
            "iteration24_artifact": digest(I24_ARTIFACT),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.write_text(content)
    args.output.with_suffix(".json.sha256").write_text(
        hashlib.sha256(content.encode()).hexdigest() + "\n"
    )
    print(
        json.dumps(
            {"output": str(args.output), "gate": output["gate"], "summary": output["summary"]},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
