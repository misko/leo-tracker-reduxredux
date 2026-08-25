#!/usr/bin/env python3
"""Post-hoc ±30 s full-catalog wrong-time extension for dwell 135219."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_wrong_time_diagnostic as base

from leo.sky.propagation import parse_element_sets


POSTHOC_SHIFTS_S = (-30.0, 30.0)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", choices=tuple(base.PATHS), required=True)
    return parser.parse_args()


def main() -> int:
    label = _arguments().path
    start_s, end_s = base.PATHS[label]
    observed_tle_digest = base.screen._file_digest(base.TLE)
    if observed_tle_digest != base.EXPECTED_TLE_DIGEST:
        raise ValueError("post-hoc wrong-time diagnostic TLE digest mismatch")

    calibration_document = base._read(base.CALIBRATION)
    catalogue = parse_element_sets(base.TLE.read_text(encoding="utf-8"))
    dataset_path = base.ROOT / f"duration-input-{label}.json"
    main_screen_path = base.ROOT / f"screen-{label}.json"
    predeclared_control_path = base.ROOT / f"wrong-time-{label}.json"
    dataset = base._read(dataset_path)
    calibration, window, inventory, scheduled_times_s = base.screen._prepare_raw_inventory(
        dataset=dataset,
        calibration_document=calibration_document,
        start_s=start_s,
        end_s=end_s,
        config=base.CONFIG,
    )
    ranking_problem = base.screen._ranking_problem(inventory.problem)
    controls = [
        base._control(
            shift_s=shift_s,
            catalogue=catalogue,
            dataset=dataset,
            scheduled_times_s=scheduled_times_s,
            ranking_problem=ranking_problem,
            raw_observations=inventory.observations,
            calibration=calibration,
        )
        for shift_s in POSTHOC_SHIFTS_S
    ]
    reference = base._main_reference(base._read(main_screen_path))
    best_wrong = min(
        controls,
        key=lambda item: item["fine_stage"]["top3"][0][
            "best_single_delta_at_zero_satellite_cost"
        ],
    )
    actual_delta = reference["best_single_delta_at_zero_satellite_cost"]
    best_wrong_delta = best_wrong["fine_stage"]["top3"][0][
        "best_single_delta_at_zero_satellite_cost"
    ]
    output = {
        "schema": "org.leo.research.posthoc-nearest-full-catalogue-wrong-time-check/v1",
        "candidate_only": True,
        "development_check_only": True,
        "post_hoc": True,
        "post_hoc_reason": (
            "requested after inspecting the fixed ±60/120/300/600 s full-catalog controls"
        ),
        "path": label,
        "prediction_utc_shifts_s": list(POSTHOC_SHIFTS_S),
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "cell_count": window.cell_count,
            "scheduled_probe_count": len(window.rows),
        },
        "configuration": base.asdict(base.CONFIG),
        "catalogue_screen_configuration": base.asdict(base.SCREEN_CONFIG),
        "observer": base.OBSERVER.model_dump(mode="json"),
        "bindings": {
            "duration_dataset_path": str(dataset_path),
            "duration_dataset_digest": base.screen._file_digest(dataset_path),
            "main_screen_path": str(main_screen_path),
            "main_screen_digest": base.screen._file_digest(main_screen_path),
            "predeclared_control_path": str(predeclared_control_path),
            "predeclared_control_digest": base.screen._file_digest(predeclared_control_path),
            "tle_path": str(base.TLE),
            "tle_digest": observed_tle_digest,
            "score_calibration_path": str(base.CALIBRATION),
            "score_calibration_digest": base.screen._file_digest(base.CALIBRATION),
            "screen_producer_path": str(Path(base.screen.__file__).resolve()),
            "screen_producer_digest": base.screen._file_digest(Path(base.screen.__file__)),
            "predeclared_diagnostic_producer_path": str(Path(base.__file__).resolve()),
            "predeclared_diagnostic_producer_digest": base.screen._file_digest(
                Path(base.__file__)
            ),
            "posthoc_producer_path": str(Path(__file__).resolve()),
            "posthoc_producer_digest": base.screen._file_digest(Path(__file__)),
            "pilot_scan_path": str(inventory.scan_path),
            "pilot_scan_digest": inventory.scan_digest,
        },
        "actual_time_reference": reference,
        "controls": controls,
        "comparison": {
            "actual_time_wins": actual_delta < best_wrong_delta,
            "actual_time_best_delta": actual_delta,
            "best_posthoc_wrong_time_shift_s": best_wrong["prediction_utc_shift_s"],
            "best_posthoc_wrong_time_best_delta": best_wrong_delta,
            "actual_time_advantage_over_best_posthoc_wrong_cost": (
                best_wrong_delta - actual_delta
            ),
        },
        "exactness": {
            "coarse_scores_all_full_window_eligible_named_catalogues": True,
            "coarse_declared_delay_grid_exhausted": True,
            "fine_declared_delay_grid_exhausted_for_refined_catalogues": True,
            "fine_catalogue_universe_pruned_to_coarse_top_32": True,
            "continuous_cfo_space_exhausted": False,
            "global_catalogue_optimum_claimed": False,
        },
    }
    output_path = base.ROOT / f"posthoc-nearest-wrong-time-{label}.json"
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
