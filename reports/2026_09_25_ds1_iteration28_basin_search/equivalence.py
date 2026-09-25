#!/usr/bin/env python3
"""Seal a fresh iteration-28 anchor-score equivalence check before search."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNNER = HERE / "run.py"
OUTPUT = HERE / "equivalence.json"


def load_runner():
    spec = importlib.util.spec_from_file_location("i28_equivalence_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise ImportError(RUNNER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    runner = load_runner()
    runner.validate_plan(runner.verified_json(runner.PLAN))
    runner.validate_inputs()
    begun = time.perf_counter()
    runner.init_worker()
    fresh = runner.score_cell_task((0.0, 0.0))
    stencil = runner.verified_json(runner.I27_STENCIL)
    prior = next(
        cell for cell in stencil["cells"] if cell["east_m"] == 0.0 and cell["north_m"] == 0.0
    )
    comparisons = []
    for group in runner.GROUPS:
        for kind in ("actual", "surrogate"):
            new_score = fresh["groups"][group][kind]
            old_score = prior["groups"][group][kind]
            comparisons.append(
                {
                    "component": f"{group}:{kind}:group_score",
                    "fresh": new_score["group_score"],
                    "iteration27": old_score["group_score"],
                    "absolute_difference": abs(new_score["group_score"] - old_score["group_score"]),
                }
            )
            for new_session, old_session in zip(
                new_score["sessions"], old_score["sessions"], strict=True
            ):
                if new_session["session_id"] != old_session["session_id"]:
                    raise ValueError("session order mismatch")
                for field in (
                    "score",
                    "occupied_second_weight",
                    "unsupported_occupied_second_weight",
                ):
                    comparisons.append(
                        {
                            "component": (f"{group}:{kind}:{new_session['session_id']}:{field}"),
                            "fresh": new_session[field],
                            "iteration27": old_session[field],
                            "absolute_difference": abs(new_session[field] - old_session[field]),
                        }
                    )
    comparisons.extend(
        [
            {
                "component": "pooled:actual",
                "fresh": fresh["actual_material_score"],
                "iteration27": prior["actual_material_score"],
                "absolute_difference": abs(
                    fresh["actual_material_score"] - prior["actual_material_score"]
                ),
            },
            {
                "component": "pooled:surrogate",
                "fresh": fresh["surrogate_score"],
                "iteration27": prior["surrogate_score"],
                "absolute_difference": abs(fresh["surrogate_score"] - prior["surrogate_score"]),
            },
        ]
    )
    maximum = max(row["absolute_difference"] for row in comparisons)
    criteria = {
        "all_score_and_session_components_match": maximum <= 1e-12,
        "atlas_direct_doppler": (
            fresh["maximum_atlas_direct_doppler_error_hz"] <= runner.MAX_ERROR_HZ
        ),
        "tail_mass": fresh["maximum_tail_mass"] <= runner.MAX_TAIL,
    }
    record = {
        "schema": "ds1-iteration28-anchor-equivalence/v1",
        "complete": True,
        "truth_used": False,
        "held_used": False,
        "elapsed_s": time.perf_counter() - begun,
        "bindings": {
            "plan": runner.digest(runner.PLAN),
            "runner": runner.digest(RUNNER),
            "equivalence_runner": runner.digest(Path(__file__)),
            "iteration27_stencil": runner.digest(runner.I27_STENCIL),
            "cache_manifest": runner.digest(runner.CACHE_MANIFEST),
        },
        "tolerance": 1e-12,
        "maximum_component_absolute_difference": maximum,
        "comparisons": comparisons,
        "maximum_atlas_direct_doppler_error_hz": fresh["maximum_atlas_direct_doppler_error_hz"],
        "maximum_tail_mass": fresh["maximum_tail_mass"],
        "gate": {"criteria": criteria, "passed": all(criteria.values())},
    }
    runner.write_sealed(OUTPUT, record)
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                "passed": record["gate"]["passed"],
                "maximum_component_absolute_difference": maximum,
                "elapsed_s": record["elapsed_s"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
