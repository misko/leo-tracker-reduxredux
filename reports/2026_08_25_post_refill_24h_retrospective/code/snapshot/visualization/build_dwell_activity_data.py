from __future__ import annotations

import json
import math
from bisect import bisect_left
from pathlib import Path

import numpy as np

from leo.analysis.research.satellite_activity import (
    ActivityGrid,
    AssociationCostModel,
    CfoCandidate,
    CfoProbe,
    DelayProfileCandidate,
    PredictedProbeCfo,
    SatelliteActivityProblem,
    SingleSatelliteHypothesis,
    decode_single_satellite,
    profile_delay_and_cfo_offset,
)
from leo.contracts.sky import ObserverSiteV1
from leo.contracts.digests import canonical_digest
from leo.sky.doppler import doppler_shift_hz
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from leo.sky.screening import observe_grid


SOURCE = Path(
    "/home/mouse9911/.codex/visualizations/2026/08/24/"
    "01a0356b-6815-70f0-85db-ee0cc2ab76da/capture-cfo-doppler-analysis.json"
)
STANDARD_ROOT = Path(
    "/srv/bulk/leo/analysis/cap-20260824T192252-9981b9c27853/"
    "capture-6f6c7e02f16b4f6dbcb260e92864adfa/scientific/path-standard/"
    "sha256:0ecd53e974bbdb9f85effaa67457c5b57799726f36d14386a1a3bfef3c7a9cd0"
)
OUTPUT = Path(__file__).with_name("dwell-activity-data.json")
TLE = """0 STARLINK-36865
1 67930U 26036AC  26236.39390955  .00015614  00000-0  57538-3 0  9992
2 67930  43.0017  17.8519 0000917 255.0713 105.0037 15.27599130 29372
"""
FIRST_SAMPLE_UTC_NS = 1_787_599_375_412_378_614
RF_FREQUENCY_HZ = 11_440_312_498.0
ACTIVITY_CELL_S = 0.1
MINIMUM_ACTIVE_CELLS = 5
GLRT_MARGIN_GATE = 0.1
DETECTION_PROBABILITY = 881.0 / 1_200.0
MATCHED_BASE_COST = -math.log(DETECTION_PROBABILITY)
MISS_COST = -math.log(1.0 - DETECTION_PROBABILITY)
SIGMA_HZ = 65.0
PROFILE_SIGMA_HZ = 100.0
SATELLITE_COST = math.log(185.0)
EPISODE_COST = math.log(300.0)
DELAY_PRIOR_SIGMA_S = 0.50


def predicted_doppler(times_s: np.ndarray, delay_s: float) -> np.ndarray:
    catalogue = parse_element_sets(TLE)
    utc_ns = tuple(
        FIRST_SAMPLE_UTC_NS + round((float(time_s) + delay_s) * 1e9)
        for time_s in times_s
    )
    grid = SamplingGrid(utc_ns=utc_ns, anchor_index=len(utc_ns) // 2, spacing_s=0.025)
    propagated = propagate_grid(catalogue, grid)
    observer = ObserverSiteV1(
        latitude_deg=37.858988,
        longitude_deg=-122.478103,
        altitude_m=-29.0,
        label="reviewed-spinnaker-sausalito-not-capture-bound",
    )
    observed = observe_grid(propagated, observer, grid)
    return np.asarray(
        doppler_shift_hz(RF_FREQUENCY_HZ, observed.range_rate_km_s[0]),
        dtype=np.float64,
    )


def main() -> None:
    source = json.loads(SOURCE.read_text())
    scan = json.loads((STANDARD_ROOT / "standard.pilot-scan.v3.json").read_text())
    dealiased = json.loads(
        (STANDARD_ROOT / "standard.dealiased-trajectory-bank.v4.json").read_text()
    )
    rows = source["plot"]["winner_glrt"]
    times = np.asarray([row["time_s"] for row in rows], dtype=np.float64)

    margin_by_source: dict[str, float] = {}
    comparison_margins = []
    for detection in scan["detections"][:1_200]:
        sample_start = int(detection["sample_start"])
        for candidate in detection["candidates"]:
            score = next(item for item in candidate["scores"] if item["method"] == "glrt64")
            source_id = canonical_digest(
                {
                    "sample_start": sample_start,
                    "candidate_rank": int(candidate["rank"]),
                    "method": "glrt64",
                }
            )
            margin_by_source[source_id] = float(score["margin"])
            if int(candidate["rank"]) >= 1:
                comparison_margins.append(float(score["margin"]))
    comparison_margins.sort()

    probes = tuple(
        CfoProbe(
            probe_id=f"probe-{index:04d}",
            time_s=float(row["time_s"]),
            cell_index=index // 4,
            missed_detection_cost=MISS_COST,
        )
        for index, row in enumerate(rows)
    )
    canonical_rows = [
        item for item in dealiased["observations"] if int(item["sample_start"]) < 75_000_000
    ]
    rows_by_component: dict[str, list[dict[str, object]]] = {}
    for item in canonical_rows:
        rows_by_component.setdefault(str(item["component_id"]), []).append(item)

    delays = tuple(round(value, 2) for value in np.arange(-2.00, 2.001, 0.05))
    all_curves = {delay: predicted_doppler(times, delay) for delay in delays}
    components = []
    for component_number, (component_id, component_rows) in enumerate(
        sorted(
            rows_by_component.items(),
            key=lambda item: min(int(row["sample_start"]) for row in item[1]),
        ),
        start=1,
    ):
        canonical_by_index: dict[int, list[dict[str, object]]] = {}
        for item in component_rows:
            index = int(item["sample_start"]) // 62_500
            canonical_by_index.setdefault(index, []).append(item)
        occupied_indices = np.asarray(sorted(canonical_by_index), dtype=np.int64)
        occupied_cfo = np.asarray(
            [
                float(
                    np.median(
                        [
                            float(item["component_cfo_hz"])
                            for item in canonical_by_index[index]
                        ]
                    )
                )
                for index in occupied_indices
            ]
        )
        profile = profile_delay_and_cfo_offset(
            occupied_cfo,
            np.full(occupied_cfo.shape, PROFILE_SIGMA_HZ),
            tuple(
                DelayProfileCandidate(
                    delay_s=delay,
                    predicted_cfo_hz=tuple(
                        float(value) for value in all_curves[delay][occupied_indices]
                    ),
                )
                for delay in delays
            ),
            delay_prior_mean_s=0.0,
            delay_prior_sigma_s=DELAY_PRIOR_SIGMA_S,
            cfo_offset_bounds_hz=(-400_000.0, 400_000.0),
        )
        best = profile.posterior_best
        best_curve = all_curves[best.delay_s]

        observations_list = []
        candidate_margin: dict[str, float] = {}
        for item in component_rows:
            source_id = str(item["source_observation_ids"][0])
            margin = margin_by_source[source_id]
            tail_count = len(comparison_margins) - bisect_left(comparison_margins, margin)
            clutter_cost = -math.log(
                (1.0 + tail_count) / (1.0 + len(comparison_margins))
            )
            observation_id = str(item["observation_id"])
            candidate_margin[observation_id] = margin
            index = int(item["sample_start"]) // 62_500
            observations_list.append(
                CfoCandidate(
                    observation_id=observation_id,
                    probe_id=f"probe-{index:04d}",
                    exclusion_group_id=source_id,
                    cfo_hz=float(item["component_cfo_hz"]),
                    sigma_hz=SIGMA_HZ,
                    clutter_cost=clutter_cost,
                    matched_base_cost=MATCHED_BASE_COST,
                    component_id=component_id,
                )
            )
        observations = tuple(observations_list)
        problem = SatelliteActivityProblem(
            grid=ActivityGrid(
                start_s=0.0,
                cell_duration_s=ACTIVITY_CELL_S,
                cell_count=len(rows) // 4,
                minimum_active_cells=MINIMUM_ACTIVE_CELLS,
                allow_left_censored=True,
                allow_right_censored=True,
            ),
            probes=probes,
            observations=observations,
            costs=AssociationCostModel(
                satellite_cost=SATELLITE_COST,
                episode_cost=EPISODE_COST,
            ),
        )
        hypothesis = SingleSatelliteHypothesis(
            hypothesis_id=f"starlink-36865-{component_id}-profiled-delay-offset",
            object_name="STARLINK-36865",
            catalog_number=67930,
            delay_s=best.delay_s,
            cfo_offset_hz=best.fitted_cfo_offset_hz,
            delay_prior_cost=best.delay_prior_cost,
            predictions=tuple(
                PredictedProbeCfo(f"probe-{index:04d}", float(best_curve[index]))
                for index in range(len(rows))
            ),
        )
        result = decode_single_satellite(problem, hypothesis)
        assigned_ids = {item.observation_id for item in result.assignments}
        assigned_by_probe: dict[str, int] = {}
        for assignment in result.assignments:
            assigned_by_probe[assignment.probe_id] = (
                assigned_by_probe.get(assignment.probe_id, 0) + 1
            )
        missed_ids = set(result.missed_probe_ids)
        predicted_aligned = best_curve + best.fitted_cfo_offset_hz
        points = []
        assigned_residuals = []
        for observation in observations:
            index = int(observation.probe_id.removeprefix("probe-"))
            observation_id = observation.observation_id
            assigned = observation_id in assigned_ids
            observed_cfo_hz = observation.cfo_hz
            residual = float(observed_cfo_hz - predicted_aligned[index])
            if assigned:
                assigned_residuals.append(residual)
            points.append(
                [
                    round(float(rows[index]["time_s"]), 3),
                    round(observed_cfo_hz, 2),
                    round(candidate_margin[observation_id], 4),
                    assigned,
                    round(residual, 2),
                ]
            )

        cells = []
        for cell_index, active in enumerate(result.activity_by_cell):
            start = cell_index * ACTIVITY_CELL_S
            probe_range = range(cell_index * 4, cell_index * 4 + 4)
            assigned_count = sum(
                assigned_by_probe.get(f"probe-{index:04d}", 0)
                for index in probe_range
            )
            missed_count = sum(
                f"probe-{index:04d}" in missed_ids for index in probe_range
            )
            cells.append([round(start, 1), active, assigned_count, missed_count])

        component_start_s = min(int(item["sample_start"]) for item in component_rows) / 2_500_000
        component_end_s = (
            max(int(item["sample_start"]) for item in component_rows) / 2_500_000 + 0.025
        )
        components.append(
            {
                "label": f"component {component_number}",
                "component_id": component_id,
                "support_s": [round(component_start_s, 3), round(component_end_s, 3)],
                "model": {
                    "selected_delay_s": best.delay_s,
                    "selected_cfo_offset_hz": round(best.fitted_cfo_offset_hz, 3),
                },
                "summary": {
                    "selected": result.selected,
                    "episode_count": len(result.episodes),
                    "active_duration_s": round(
                        sum(result.activity_by_cell) * ACTIVITY_CELL_S, 3
                    ),
                    "canonical_candidate_count": len(observations),
                    "occupied_probe_count": len(occupied_indices),
                    "assignment_count": len(result.assignments),
                    "missed_probe_count": len(result.missed_probe_ids),
                    "unassigned_candidate_count": len(result.unexplained_observation_ids),
                    "assigned_residual_rms_hz": round(
                        float(np.sqrt(np.mean(np.square(assigned_residuals)))), 3
                    ),
                    "assigned_residual_median_absolute_hz": round(
                        float(np.median(np.abs(assigned_residuals))), 3
                    ),
                    "null_cost": round(result.objective.null_cost, 3),
                    "selected_cost": round(result.objective.total_cost, 3),
                    "delta_from_null": round(result.objective.delta_from_null, 3),
                },
                "episodes": [
                    {
                        "start_s": round(item.start_cell * ACTIVITY_CELL_S, 1),
                        "end_s": round(
                            item.end_cell_exclusive * ACTIVITY_CELL_S, 1
                        ),
                        "duration_s": round(item.duration_s, 1),
                    }
                    for item in result.episodes
                ],
                "profile": [
                    [
                        item.delay_s,
                        round(item.fitted_cfo_offset_hz, 3),
                        round(item.data_cost, 4),
                        round(item.delay_prior_cost, 4),
                        round(item.total_cost, 4),
                    ]
                    for item in profile.points
                ],
                "profile_diagnostics": {
                    "data_flat": profile.data_flat,
                    "data_ambiguous": profile.data_ambiguous,
                    "posterior_differs_from_data_only": profile.posterior_differs_from_data_only,
                    "delay_prior_dominated": profile.delay_prior_dominated,
                    "posterior_at_delay_boundary": profile.posterior_at_delay_boundary,
                },
                "curve": [
                    [
                        round(float(times[index]), 3),
                        round(float(predicted_aligned[index]), 2),
                    ]
                    for index in range(len(times))
                ],
                "points": points,
                "cells": cells,
            }
        )

    output = {
        "source": {
            "capture": "cap-20260824T192252-9981b9c27853",
            "path": "radio_pluto_19f2 / stream-1 / RX1 / upper edge",
            "interval_s": [0.0, 30.0],
            "sample_zero_utc": "2026-08-24T19:22:55.412378614Z",
            "candidate_conditioning": "source-selected positive-replay GLRT branch observations",
            "observer": "reviewed Sausalito preset; not capture-bound GPS",
        },
        "model": {
            "satellite": "STARLINK-36865 / NORAD 67930",
            "delay_grid_s": list(delays),
            "delay_prior_mean_s": 0.0,
            "delay_prior_sigma_s": DELAY_PRIOR_SIGMA_S,
            "sigma_hz": SIGMA_HZ,
            "profile_sigma_hz": PROFILE_SIGMA_HZ,
            "margin_gate": GLRT_MARGIN_GATE,
            "empirical_comparison_margin_count": len(comparison_margins),
            "matched_base_cost": round(MATCHED_BASE_COST, 6),
            "miss_cost": round(MISS_COST, 6),
            "satellite_cost": round(SATELLITE_COST, 6),
            "episode_cost": EPISODE_COST,
            "activity_cell_s": ACTIVITY_CELL_S,
            "minimum_active_s": ACTIVITY_CELL_S * MINIMUM_ACTIVE_CELLS,
        },
        "summary": {
            "scheduled_probe_count": len(probes),
            "canonical_candidate_count": len(canonical_rows),
            "component_count": len(components),
        },
        "components": components,
    }
    OUTPUT.write_text(json.dumps(output, separators=(",", ":")))
    print(
        json.dumps(
            {
                "output": str(OUTPUT),
                **output["summary"],
                **output["model"],
                "components": [
                    {
                        "label": component["label"],
                        "support_s": component["support_s"],
                        **component["model"],
                        **component["summary"],
                        "profile_diagnostics": component["profile_diagnostics"],
                    }
                    for component in components
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
