#!/usr/bin/env python3
"""Predeclared full-catalog wrong-orbital-time controls for dwell 135219."""

# ruff: noqa: E402,I001 -- repository tools are imported after the explicit root binding.

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

REPOSITORY = Path("/home/mouse9911/gits/leo-tracker-reduxredux")
if str(REPOSITORY) not in sys.path:
    sys.path.insert(0, str(REPOSITORY))

from leo.contracts.sky import ObserverSiteV1
from leo.sky.propagation import parse_element_sets
from tools import replay_raw_grouped_satellite_activity as raw_replay
from tools import screen_raw_satellite_activity_catalog as screen
from tools.raw_satellite_activity_search_configuration import CatalogueScreenConfig


ROOT = Path(__file__).resolve().parent
CALIBRATION = (
    REPOSITORY
    / "reports/figures/2026_08_25_raw_satellite_activity_calibration/score-calibration-v3.json"
)
TLE = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/22/"
    "01a02af8-cec4-7703-a883-75760f132c40/"
    "radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle"
)
EXPECTED_TLE_DIGEST = (
    "sha256:ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee"
)
TIME_SHIFTS_S = (-600.0, -300.0, -120.0, -60.0, 60.0, 120.0, 300.0, 600.0)
PATHS = {
    "5d4d-rx0": (4.5, 16.3),
    "5d4d-rx1": (4.5, 16.3),
    "19f2-rx0": (4.4, 16.2),
    "19f2-rx1": (4.4, 16.2),
}
OBSERVER = ObserverSiteV1(
    latitude_deg=37.858988,
    longitude_deg=-122.478103,
    altitude_m=-29.0,
    label="spinnaker-sausalito",
)
CONFIG = raw_replay.RawReplayConfig(
    cell_duration_s=0.1,
    minimum_active_duration_s=0.5,
    allow_left_censored=False,
    allow_right_censored=False,
    cfo_sigma_hz=100.0,
    satellite_cost=5.25,
    episode_cost=5.75,
    huber_threshold=1.345,
    delay_min_s=-2.0,
    delay_max_s=2.0,
    delay_step_s=0.1,
    delay_prior_mean_s=0.0,
    delay_prior_sigma_s=0.5,
    duplicate_cfo_tolerance_hz=0.0,
    resolution_epoch_tolerance_samples=1,
    resolution_tracking_cfo_tolerance_hz=500.0,
    mode_bin_hz=100.0,
    mode_half_width_hz=300.0,
    modes_per_delay=2,
    retained_states_per_catalog=4,
    maximum_state_combinations=256,
    horizon_mask_deg=0.0,
)
SCREEN_CONFIG = CatalogueScreenConfig(
    name_prefix="STARLINK",
    geometry_spacing_s=0.5,
    coarse_delay_step_s=0.5,
    coarse_modes_per_delay=1,
    refinement_catalog_count=32,
    refinement_guard_cost=0.0,
    maximum_refinement_catalog_count=64,
    final_catalog_count=3,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", choices=tuple(PATHS), required=True)
    return parser.parse_args()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _main_reference(document: dict[str, Any]) -> dict[str, Any]:
    fine = document["catalogue_search"]["fine_stage"]
    return {
        "prediction_utc_shift_s": 0.0,
        "fine_top3": fine["ranking"][:3],
        "best_single_delta_at_zero_satellite_cost": fine["ranking"][0][
            "best_single_delta_at_zero_satellite_cost"
        ],
        "source": "frozen_main_unseeded_fine_screen",
    }


def _control(
    *,
    shift_s: float,
    catalogue: Any,
    dataset: dict[str, Any],
    scheduled_times_s: tuple[float, ...],
    ranking_problem: Any,
    raw_observations: Any,
    calibration: Any,
) -> dict[str, Any]:
    coarse_delay_grid = screen._strict_delay_grid(
        CONFIG.delay_min_s,
        CONFIG.delay_max_s,
        SCREEN_CONFIG.coarse_delay_step_s,
    )
    prediction_delay_grid = tuple(sorted(set(CONFIG.delay_grid) | set(coarse_delay_grid)))
    bank = screen.build_catalogue_prediction_bank(
        catalogue=catalogue,
        scheduled_times_s=scheduled_times_s,
        first_sample_utc_ns=(
            int(dataset["timing_binding"]["first_estimate_utc_ns"])
            + round(shift_s * 1e9)
        ),
        delay_grid=prediction_delay_grid,
        sky_frequency_hz=float(dataset["frequency_binding"]["sky_frequency_hz"]),
        observer=OBSERVER,
        horizon_mask_deg=CONFIG.horizon_mask_deg,
        name_prefix=SCREEN_CONFIG.name_prefix,
        geometry_spacing_s=SCREEN_CONFIG.geometry_spacing_s,
    )
    coarse_config = replace(
        CONFIG,
        delay_step_s=SCREEN_CONFIG.coarse_delay_step_s,
        modes_per_delay=SCREEN_CONFIG.coarse_modes_per_delay,
        satellite_cost=0.0,
    )
    fine_config = replace(CONFIG, satellite_cost=0.0)
    coarse_scores = screen._score_catalog_rows(
        bank=bank,
        row_indices=tuple(range(len(bank.catalogue_indices))),
        delay_grid=coarse_delay_grid,
        problem=ranking_problem,
        raw_observations=raw_observations,
        calibration=calibration,
        config=coarse_config,
    )
    refinement_catalogue_indices = screen._refinement_rows(coarse_scores, SCREEN_CONFIG)
    bank_row_by_catalogue_index = {
        catalogue_index: row for row, catalogue_index in enumerate(bank.catalogue_indices)
    }
    refinement_rows = tuple(
        bank_row_by_catalogue_index[index] for index in refinement_catalogue_indices
    )
    fine_scores = screen._score_catalog_rows(
        bank=bank,
        row_indices=refinement_rows,
        delay_grid=CONFIG.delay_grid,
        problem=ranking_problem,
        raw_observations=raw_observations,
        calibration=calibration,
        config=fine_config,
    )
    return {
        "prediction_utc_shift_s": shift_s,
        "geometry_accounting": asdict(bank.accounting),
        "coarse_stage": {
            "eligible_catalog_count": len(coarse_scores),
            "generated_state_count": sum(item.generated_state_count for item in coarse_scores),
            "declared_delay_grid_exhausted": True,
            "data_proposed_cfo_mode_space_exhausted": False,
            "top3": [
                screen._score_summary(item, rank)
                for rank, item in enumerate(coarse_scores[:3], start=1)
            ],
        },
        "fine_stage": {
            "refinement_catalog_count": len(fine_scores),
            "generated_state_count": sum(item.generated_state_count for item in fine_scores),
            "eligible_catalogue_state_space_exhausted": len(fine_scores)
            == len(coarse_scores),
            "declared_delay_grid_exhausted_per_refined_catalog": True,
            "data_proposed_cfo_mode_space_exhausted": False,
            "top3": [
                screen._score_summary(item, rank)
                for rank, item in enumerate(fine_scores[:3], start=1)
            ],
        },
    }


def main() -> int:
    label = _arguments().path
    start_s, end_s = PATHS[label]
    observed_tle_digest = screen._file_digest(TLE)
    if observed_tle_digest != EXPECTED_TLE_DIGEST:
        raise ValueError("wrong-time diagnostic TLE digest mismatch")
    calibration_document = _read(CALIBRATION)
    catalogue = parse_element_sets(TLE.read_text(encoding="utf-8"))
    dataset_path = ROOT / f"duration-input-{label}.json"
    main_screen_path = ROOT / f"screen-{label}.json"
    dataset = _read(dataset_path)
    calibration, window, inventory, scheduled_times_s = screen._prepare_raw_inventory(
        dataset=dataset,
        calibration_document=calibration_document,
        start_s=start_s,
        end_s=end_s,
        config=CONFIG,
    )
    ranking_problem = screen._ranking_problem(inventory.problem)
    controls = [
        _control(
            shift_s=shift_s,
            catalogue=catalogue,
            dataset=dataset,
            scheduled_times_s=scheduled_times_s,
            ranking_problem=ranking_problem,
            raw_observations=inventory.observations,
            calibration=calibration,
        )
        for shift_s in TIME_SHIFTS_S
    ]
    reference = _main_reference(_read(main_screen_path))
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
        "schema": "org.leo.research.full-catalogue-wrong-orbital-time-development-check/v1",
        "candidate_only": True,
        "development_check_only": True,
        "path": label,
        "predeclared_prediction_utc_shifts_s": list(TIME_SHIFTS_S),
        "window": {
            "start_s": start_s,
            "end_s": end_s,
            "cell_count": window.cell_count,
            "scheduled_probe_count": len(window.rows),
        },
        "configuration": asdict(CONFIG),
        "catalogue_screen_configuration": asdict(SCREEN_CONFIG),
        "observer": OBSERVER.model_dump(mode="json"),
        "bindings": {
            "duration_dataset_path": str(dataset_path),
            "duration_dataset_digest": screen._file_digest(dataset_path),
            "main_screen_path": str(main_screen_path),
            "main_screen_digest": screen._file_digest(main_screen_path),
            "tle_path": str(TLE),
            "tle_digest": observed_tle_digest,
            "score_calibration_path": str(CALIBRATION),
            "score_calibration_digest": screen._file_digest(CALIBRATION),
            "screen_producer_path": str(Path(screen.__file__).resolve()),
            "screen_producer_digest": screen._file_digest(Path(screen.__file__)),
            "diagnostic_producer_path": str(Path(__file__).resolve()),
            "diagnostic_producer_digest": screen._file_digest(Path(__file__)),
            "pilot_scan_path": str(inventory.scan_path),
            "pilot_scan_digest": inventory.scan_digest,
        },
        "actual_time_reference": reference,
        "controls": controls,
        "comparison": {
            "actual_time_wins": actual_delta < best_wrong_delta,
            "actual_time_best_delta": actual_delta,
            "best_wrong_time_shift_s": best_wrong["prediction_utc_shift_s"],
            "best_wrong_time_best_delta": best_wrong_delta,
            "actual_time_advantage_over_best_wrong_cost": best_wrong_delta - actual_delta,
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
    output_path = ROOT / f"wrong-time-{label}.json"
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
