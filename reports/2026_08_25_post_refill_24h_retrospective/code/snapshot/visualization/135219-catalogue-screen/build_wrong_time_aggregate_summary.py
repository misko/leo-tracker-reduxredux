#!/usr/bin/env python3
"""Aggregate frozen per-path true-time and wrong-time catalogue minima."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPOSITORY = Path("/home/mouse9911/gits/leo-tracker-reduxredux")
MULTIPATH_PRODUCER = REPOSITORY / "tools/replay_raw_multipath_satellite_activity.py"
PATHS = ("5d4d-rx0", "5d4d-rx1", "19f2-rx0", "19f2-rx1")
PREDECLARED_SHIFTS = (-600.0, -300.0, -120.0, -60.0, 60.0, 120.0, 300.0, 600.0)
POSTHOC_SHIFTS = (-30.0, 30.0)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _best(control: dict[str, Any]) -> dict[str, Any]:
    item = control["fine_stage"]["top3"][0]
    return {
        "catalog_number": item["catalog_number"],
        "object_name": item["object_name"],
        "delay_s": item["best_delay_s"],
        "best_single_delta_at_zero_satellite_cost": item[
            "best_single_delta_at_zero_satellite_cost"
        ],
    }


def _aggregate(
    controls_by_path: dict[str, dict[str, Any]], shifts: tuple[float, ...]
) -> list[dict[str, Any]]:
    result = []
    for shift in shifts:
        paths = []
        for label in PATHS:
            controls = controls_by_path[label]["controls"]
            matches = [item for item in controls if item["prediction_utc_shift_s"] == shift]
            if len(matches) != 1:
                raise ValueError(f"{label} does not contain exactly one {shift:+g} s control")
            paths.append({"path": label, **_best(matches[0])})
        result.append(
            {
                "prediction_utc_shift_s": shift,
                "path_minima": paths,
                "sum_best_single_delta_at_zero_satellite_cost": sum(
                    item["best_single_delta_at_zero_satellite_cost"] for item in paths
                ),
                "unanimous_catalog_number": (
                    paths[0]["catalog_number"]
                    if len({item["catalog_number"] for item in paths}) == 1
                    else None
                ),
            }
        )
    return result


def main() -> int:
    predeclared_paths = {label: ROOT / f"wrong-time-{label}.json" for label in PATHS}
    posthoc_paths = {
        label: ROOT / f"posthoc-nearest-wrong-time-{label}.json" for label in PATHS
    }
    predeclared = {label: _read(path) for label, path in predeclared_paths.items()}
    posthoc = {label: _read(path) for label, path in posthoc_paths.items()}
    if any(
        tuple(document["predeclared_prediction_utc_shifts_s"]) != PREDECLARED_SHIFTS
        for document in predeclared.values()
    ):
        raise ValueError("predeclared shift set changed")
    if any(
        tuple(document["prediction_utc_shifts_s"]) != POSTHOC_SHIFTS
        or document.get("post_hoc") is not True
        for document in posthoc.values()
    ):
        raise ValueError("post-hoc shift set or label changed")

    actual_paths = []
    for label in PATHS:
        reference = predeclared[label]["actual_time_reference"]
        best = reference["fine_top3"][0]
        actual_paths.append(
            {
                "path": label,
                "catalog_number": best["catalog_number"],
                "object_name": best["object_name"],
                "delay_s": best["best_delay_s"],
                "best_single_delta_at_zero_satellite_cost": best[
                    "best_single_delta_at_zero_satellite_cost"
                ],
            }
        )
    actual_sum = sum(
        item["best_single_delta_at_zero_satellite_cost"] for item in actual_paths
    )
    predeclared_aggregate = _aggregate(predeclared, PREDECLARED_SHIFTS)
    posthoc_aggregate = _aggregate(posthoc, POSTHOC_SHIFTS)
    best_predeclared = min(
        predeclared_aggregate,
        key=lambda item: item["sum_best_single_delta_at_zero_satellite_cost"],
    )
    best_posthoc = min(
        posthoc_aggregate,
        key=lambda item: item["sum_best_single_delta_at_zero_satellite_cost"],
    )
    output = {
        "schema": "org.leo.research.four-path-wrong-time-catalogue-minima-summary/v1",
        "candidate_only": True,
        "specificity_claimed": False,
        "comparison_metric": (
            "sum across paths of each independent full-catalog fine-stage minimum at zero "
            "satellite cost"
        ),
        "bindings": {
            "producer_path": str(Path(__file__).resolve()),
            "producer_digest": _digest(Path(__file__)),
            "predeclared_controls": [
                {"path": str(path), "digest": _digest(path)}
                for path in predeclared_paths.values()
            ],
            "posthoc_controls": [
                {"path": str(path), "digest": _digest(path)}
                for path in posthoc_paths.values()
            ],
            "current_multipath_producer": {
                "path": str(MULTIPATH_PRODUCER),
                "digest": _digest(MULTIPATH_PRODUCER),
            },
        },
        "actual_time": {
            "prediction_utc_shift_s": 0.0,
            "path_minima": actual_paths,
            "sum_best_single_delta_at_zero_satellite_cost": actual_sum,
            "unanimous_catalog_number": 58789,
        },
        "predeclared_controls": predeclared_aggregate,
        "predeclared_comparison": {
            "actual_beats_every_predeclared_aggregate_shift": actual_sum
            < best_predeclared["sum_best_single_delta_at_zero_satellite_cost"],
            "best_predeclared_shift_s": best_predeclared["prediction_utc_shift_s"],
            "best_predeclared_sum": best_predeclared[
                "sum_best_single_delta_at_zero_satellite_cost"
            ],
            "actual_advantage_cost": best_predeclared[
                "sum_best_single_delta_at_zero_satellite_cost"
            ]
            - actual_sum,
        },
        "posthoc_nearest_controls": posthoc_aggregate,
        "posthoc_comparison": {
            "post_hoc": True,
            "actual_beats_both_posthoc_aggregate_shifts": actual_sum
            < best_posthoc["sum_best_single_delta_at_zero_satellite_cost"],
            "best_posthoc_shift_s": best_posthoc["prediction_utc_shift_s"],
            "best_posthoc_sum": best_posthoc[
                "sum_best_single_delta_at_zero_satellite_cost"
            ],
            "actual_advantage_cost": best_posthoc[
                "sum_best_single_delta_at_zero_satellite_cost"
            ]
            - actual_sum,
        },
        "specificity_verdict": {
            "result": "fail",
            "reason": (
                "post-hoc +30 s full-catalog control has a lower four-path aggregate minimum "
                "than the actual-time catalogue screen"
            ),
            "winning_wrong_time_shift_s": best_posthoc["prediction_utc_shift_s"],
            "winning_wrong_time_catalog_number": best_posthoc["unanimous_catalog_number"],
            "wrong_time_improvement_cost": actual_sum
            - best_posthoc["sum_best_single_delta_at_zero_satellite_cost"],
        },
        "exactness": {
            "aggregation_exact_over_persisted_path_minima": True,
            "source_screens_coarse_score_all_full_window_eligible_catalogues": True,
            "source_screens_fine_refinement_pruned_to_coarse_top_32": True,
            "source_screens_use_data_proposed_cfo_modes": True,
            "global_catalogue_optimum_claimed": False,
        },
        "required_multipath_model_extension": {
            "status": "not_representable_by_current_v2_schema",
            "required_parameter": "prediction_utc_shift_s_per_catalogue_hypothesis",
            "required_bindings": [
                "CLI_or_input_contract",
                "search_configuration_digest",
                "hypothesis_id",
                "serialized_nuisance_state",
            ],
            "reason": (
                "the specificity challenger is NORAD 63280 propagated at +30 s while the "
                "true-time candidate is NORAD 58789 propagated at 0 s; current v2 applies "
                "one persisted probe UTC epoch to every supplied catalogue"
            ),
            "misleading_actual_time_only_shared_replay_omitted": True,
            "nonstandard_monkeypatched_replay_omitted": True,
        },
    }
    (ROOT / "wrong-time-aggregate-summary.json").write_text(
        json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
