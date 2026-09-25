#!/usr/bin/env python3
"""Prospective DS3 iteration-32 session-nominal basin closure.

This wrapper reuses the reviewed cached successor engine without changing it.
It owns only a new, isolated plan, inference, replay, and qualification tree.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
ENGINE_PATH = (
    ROOT / "reports/2026_09_25_ds3_all_iterations_backfill/batch-b/successor_adapter_cached.py"
)
PARENT = (
    ROOT / "reports/2026_09_25_ds3_all_iterations_backfill/batch-b-output/"
    "iteration-21/inference.json"
)
SUPPORT = (
    ROOT / "reports/2026_09_25_ds3_all_iterations_backfill/batch-b-output/"
    "iteration-20/support-for-next.json"
)
PLAN = HERE / "plan-v2.json"
INFERENCE = HERE / "inference.json"
REPLAY = HERE / "replay.json"
RAW_INFERENCE = HERE / "raw-inference.json"
RAW_REPLAY = HERE / "raw-replay.json"
QUALIFICATION = HERE / "qualification.json"
CHECKPOINTS = HERE / "checkpoints"
REPLAY_CHECKPOINTS = HERE / "replay-checkpoints"
ITERATION = 32
CONFIG = {
    "association": "frozen",
    "selector": "session_nominal",
    "stages": (
        (0.048828125, 32),
        (0.0244140625, 8),
        (0.01220703125, 8),
    ),
    "rate_bound": 0.50,
}


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def load_engine() -> Any:
    name = "ds3_iteration32_successor_engine"
    if name in sys.modules:
        engine = sys.modules[name]
    else:
        spec = importlib.util.spec_from_file_location(name, ENGINE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(ENGINE_PATH)
        engine = importlib.util.module_from_spec(spec)
        sys.modules[name] = engine
        spec.loader.exec_module(engine)
    engine.CONFIG[ITERATION] = CONFIG
    return engine


def plan_value(engine: Any) -> dict[str, Any]:
    parent = engine.validate_parent(PARENT)
    engine.validate_support(SUPPORT)
    dependencies = (
        Path(__file__),
        ENGINE_PATH,
        engine.I12_ADAPTER,
        engine.JOINT,
        engine.ORBIT,
        engine.ORBIT_RUNNER,
    )
    return {
        "schema": "ds3-successor-plan/v1",
        "experiment_id": "ds3-iteration32-session-nominal-closure",
        "complete": True,
        "iteration": ITERATION,
        "dataset_scope": "DS3/all56",
        "reference_coordinate_present": False,
        "reference_used_for_inference": False,
        "held_observations_used": False,
        "parent": {"path": str(PARENT), "sha256": digest(PARENT)},
        "parent_qualification": {
            "terminal_status": parent.get("terminal_status"),
            "qualified": bool(parent.get("qualified", False)),
        },
        "support": {"path": str(SUPPORT), "sha256": digest(SUPPORT)},
        "method": {
            **CONFIG,
            "stages": [
                {"spacing_km": spacing, "maximum_translations": translations}
                for spacing, translations in CONFIG["stages"]
            ],
            "rate_boundary_margin_s_h": 1e-6,
            "timing_refresh": {
                "node_count": 9,
                "spacing_s": 0.05,
                "maximum_translations": 4,
                "applied": False,
            },
            "group_weight_rule": (
                "reuse sealed DS3 I20 RF-only occupied-second support times local "
                "frequency-curvature weights, normalized"
            ),
            "selection_objective": (
                "per-session mean of per-track mean-squared residual capped at "
                "800 Hz, RF-weighted across the two sealed interleaves"
            ),
            "fitted_parameters": [
                "receiver latitude and longitude",
                "one profiled constant CFO per frozen track",
            ],
            "frozen_parameters": [
                "DS3-local hard candidate identity per track",
                "DS3-local interleave receive-time offsets",
                "DS3-local RF group weights",
            ],
            "nonselecting_final_audit": (
                "per-NORAD causal phase rates with active-set widening from "
                "+/-0.25 to +/-0.50 s/hour and direct SGP4 replay"
            ),
            "stopping_rule": (
                "advance only after an interior 3x3 winner; fail closed after the "
                "declared translation budget; never inspect reference error"
            ),
        },
        "dependencies": [
            {"path": str(path.resolve()), "sha256": digest(path)} for path in dependencies
        ],
        "parent_coordinate": engine.coordinate(parent),
    }


def create_plan() -> dict[str, Any]:
    engine = load_engine()
    if PLAN.exists():
        value = engine.verify(PLAN)
        if value != plan_value(engine):
            raise ValueError("existing plan does not match prospective contract")
        return value
    value = plan_value(engine)
    engine.write(PLAN, value)
    return value


def scientific_replay_view(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "terminal_status": value.get("terminal_status"),
        "qualified": value.get("qualified"),
        "winner": value.get("winner"),
        "final_widened_rate_audit": value.get("final_widened_rate_audit"),
        "step_winners": [
            {
                "winner": row.get("winner"),
                "winner_on_edge": row.get("winner_on_edge"),
            }
            for row in value.get("steps", [])
        ],
    }


def run_inference(*, replay: bool, workers: int) -> dict[str, Any]:
    engine = load_engine()
    create_plan()
    output = REPLAY if replay else INFERENCE
    if output.exists():
        return engine.verify(output)
    raw_output = RAW_REPLAY if replay else RAW_INFERENCE
    checkpoints = REPLAY_CHECKPOINTS if replay else CHECKPOINTS
    raw = engine.run(PLAN, raw_output, checkpoints, workers)
    audit_begun = time.perf_counter()
    final_rate_audit: list[dict[str, Any]] = []
    status = str(raw["terminal_status"])
    if status == "qualified":
        initialization = engine.verify(Path(raw["initialization"]["path"]))
        final_rate_audit = engine._final_widened_rate_audit(raw["winner"], initialization["groups"])
        status = engine._terminal_status(
            complete=True,
            winner=raw["winner"],
            timing_failed=False,
            requires_final_rate_audit=True,
            final_rate_audit=final_rate_audit,
        )
    result = {
        **raw,
        "schema": "ds3-iteration32-session-nominal-inference/v1",
        "terminal_status": status,
        "qualified": status == "qualified",
        "final_widened_rate_audit": final_rate_audit,
        "elapsed_s": float(raw["elapsed_s"]) + (time.perf_counter() - audit_begun),
        "cached_engine_result": {
            "path": str(raw_output.resolve()),
            "sha256": digest(raw_output),
        },
    }
    engine.write(output, result)
    return result


def qualify() -> dict[str, Any]:
    engine = load_engine()
    plan = engine.validate_plan(PLAN)
    inference = engine.verify(INFERENCE)
    replay = engine.verify(REPLAY)
    primary_view = scientific_replay_view(inference)
    replay_view = scientific_replay_view(replay)
    audits = inference.get("final_widened_rate_audit", [])
    criteria = {
        "plan_blind": all(
            plan.get(key) is False
            for key in (
                "reference_coordinate_present",
                "reference_used_for_inference",
                "held_observations_used",
            )
        ),
        "inference_blind": all(
            inference.get(key) is False
            for key in (
                "reference_coordinate_present",
                "reference_used_for_inference",
                "held_observations_used",
            )
        ),
        "interior_closure": inference.get("terminal_status") == "qualified",
        "all_fits_converged": bool(inference.get("winner", {}).get("all_converged")),
        "no_selection_rate_boundary": (inference.get("winner", {}).get("rate_boundary_count") == 0),
        "final_rate_audit_present": len(audits) == 2,
        "final_rate_audit_converged": bool(audits)
        and all(row.get("fit_converged") is True for row in audits),
        "no_final_rate_boundary": bool(audits)
        and all(row.get("effective_boundary_rate_count") == 0 for row in audits),
        "exact_sgp4_replay": bool(audits)
        and all(row.get("exact_sgp4_gate", {}).get("passed") is True for row in audits),
        "deterministic_replay": primary_view == replay_view,
    }
    value = {
        "schema": "ds3-iteration32-session-nominal-qualification/v1",
        "complete": True,
        "qualified": all(criteria.values()),
        "terminal_status": (
            "qualified" if all(criteria.values()) else inference.get("terminal_status")
        ),
        "criteria": criteria,
        "bindings": {
            "plan": digest(PLAN),
            "inference": digest(INFERENCE),
            "replay": digest(REPLAY),
        },
        "deterministic_replay": {
            "matched": primary_view == replay_view,
            "primary_scientific_sha256": "sha256:"
            + hashlib.sha256(canonical(primary_view).encode()).hexdigest(),
            "replay_scientific_sha256": "sha256:"
            + hashlib.sha256(canonical(replay_view).encode()).hexdigest(),
        },
        "winner": inference.get("winner"),
        "inference_elapsed_s": inference.get("elapsed_s"),
        "replay_elapsed_s": replay.get("elapsed_s"),
        "reference_coordinate_present": False,
        "reference_used_for_inference": False,
        "held_observations_used": False,
    }
    if QUALIFICATION.exists():
        existing = engine.verify(QUALIFICATION)
        if existing != value:
            raise ValueError("qualification already exists with different content")
        return existing
    engine.write(QUALIFICATION, value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    infer = sub.add_parser("infer")
    infer.add_argument("--workers", type=int, default=2)
    replay = sub.add_parser("replay")
    replay.add_argument("--workers", type=int, default=2)
    sub.add_parser("qualify")
    args = parser.parse_args()
    if args.command == "plan":
        create_plan()
    elif args.command == "infer":
        run_inference(replay=False, workers=args.workers)
    elif args.command == "replay":
        run_inference(replay=True, workers=args.workers)
    else:
        qualify()


if __name__ == "__main__":
    main()
