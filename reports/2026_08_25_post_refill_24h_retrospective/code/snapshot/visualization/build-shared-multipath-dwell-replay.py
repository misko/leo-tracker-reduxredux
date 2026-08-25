from __future__ import annotations

import json
import math
from pathlib import Path


REPOSITORY = Path("/home/mouse9911/gits/leo-tracker-reduxredux")
SOURCE = REPOSITORY / (
    "reports/figures/2026_08_25_103607_satellite_activity/"
    "raw-multipath-catalogue-utc-46-60-score-v3-wide-posthoc.json"
)
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "shared-multipath-dwell-replay.template.html"
OUTPUT = HERE / "shared-multipath-dwell-replay.html"


def _path_label(path_id: str) -> str:
    fields = path_id.split(":")
    radio = "19f2" if "19f2" in fields[0] else "5d4d"
    receiver = fields[1].upper()
    return f"{radio} {receiver}"


def main() -> None:
    source = json.loads(SOURCE.read_text())
    selected = next(
        satellite
        for satellite in source["association"]["satellites"]
        if satellite["selected"]
    )
    hypothesis_id = selected["hypothesis_id"]
    detailed_paths = source["selected_path_assignment_details"][hypothesis_id]["paths"]
    path_objectives = {
        row["path_id"]: row
        for row in source["path_full_persisted_inventory_objectives"]
    }
    inventories = {row["path_id"]: row for row in source["path_inventories"]}

    start_ns = int(source["window"]["start_utc_ns"])
    cell_duration_s = float(source["window"]["cell_duration_s"])
    episodes = [
        [
            float(row["start_cell"]) * cell_duration_s,
            float(row["end_cell_exclusive"]) * cell_duration_s,
        ]
        for row in selected["episodes"]
    ]

    paths = []
    for selected_path in selected["paths"]:
        path_id = selected_path["path_id"]
        cfo_offset_hz = float(selected_path["cfo_offset_hz"])
        assignments = sorted(
            detailed_paths[path_id]["assignments"],
            key=lambda row: (int(row["estimate_utc_ns"]), str(row["observation_id"])),
        )
        points = [
            [
                round((int(row["estimate_utc_ns"]) - start_ns) / 1e9, 6),
                round(float(row["observed_cfo_hz"]) - cfo_offset_hz, 3),
                round(float(row["geometric_doppler_hz"]), 3),
                round(float(row["residual_hz"]), 3),
                round(float(row["glrt64_margin"]), 5),
                int(row["candidate_rank"]),
            ]
            for row in assignments
        ]
        residual_rms = math.sqrt(
            sum(point[3] * point[3] for point in points) / len(points)
        )
        inventory = inventories[path_id]
        objective = path_objectives[path_id]
        paths.append(
            {
                "id": path_id,
                "label": _path_label(path_id),
                "rf_ghz": round(float(inventory["sky_frequency_hz"]) / 1e9, 6),
                "cfo_offset_hz": round(cfo_offset_hz, 3),
                "assignments": len(points),
                "misses": len(selected_path["missed_probe_ids"]),
                "residual_rms_hz": round(residual_rms, 3),
                "delta_from_null": round(float(objective["delta_from_null"]), 6),
                "points": points,
            }
        )

    candidate_rows = []
    for catalog in source["nuisance_state_search"]["catalogs"]:
        best = min(
            catalog["states"], key=lambda row: float(row["single_satellite_delta_from_null"])
        )
        candidate_rows.append(
            {
                "catalog_number": int(catalog["catalog_number"]),
                "object_name": str(best["object_name"]),
                "delay_s": round(float(best["delay_s"]), 3),
                "delay_at_boundary": bool(
                    best["delay_at_lower_grid_boundary"]
                    or best["delay_at_upper_grid_boundary"]
                ),
                "delta_from_null": round(
                    float(best["single_satellite_delta_from_null"]), 6
                ),
                "selected": int(catalog["catalog_number"])
                in source["decision"]["selected_catalog_numbers"],
            }
        )

    objective = source["association"]["objective"]
    structural_cost = (
        float(objective["satellite_cost"])
        + float(objective["episode_cost"])
        + float(objective["delay_prior_cost"])
    )
    output_data = {
        "capture": "103607",
        "window_duration_s": round(
            (int(source["window"]["end_utc_ns"]) - start_ns) / 1e9, 6
        ),
        "minimum_active_duration_s": float(
            source["window"]["minimum_active_duration_s"]
        ),
        "candidate": {
            "catalog_number": int(selected["catalog_number"]),
            "object_name": str(selected["object_name"]),
            "delay_s": float(selected["delay_s"]),
            "episodes": episodes,
        },
        "paths": paths,
        "candidate_rows": candidate_rows,
        "objective": {
            "null_cost": round(float(objective["null_cost"]), 6),
            "total_cost": round(float(objective["total_cost"]), 6),
            "delta_from_null": round(float(objective["delta_from_null"]), 6),
            "structural_and_prior_cost": round(structural_cost, 6),
        },
        "search": {
            "catalogue_search_performed": bool(source["catalogue_search_performed"]),
            "catalogue_search_exact": bool(source["catalogue_search_exact"]),
            "explicit_catalog_count": len(source["nuisance_state_search"]["catalogs"]),
            "states_per_catalog": [
                int(row["generated_state_count"])
                for row in source["nuisance_state_search"]["catalogs"]
            ],
            "retained_state_count_per_catalog": [
                int(row["retained_state_count"])
                for row in source["nuisance_state_search"]["catalogs"]
            ],
            "joint_combinations_evaluated": int(
                source["nuisance_state_search"][
                    "evaluated_retained_joint_state_combination_count"
                ]
            ),
        },
        "claims": {
            "candidate_only": bool(source["candidate_only"]),
            "specificity_claimed": bool(source["specificity_claimed"]),
            "payload_decoded": bool(source["payload_decoded"]),
            "structural_costs_calibrated": bool(source["structural_costs_calibrated"]),
            "full_window_shared_band_occupancy_assumed": bool(
                source["full_window_shared_band_occupancy_assumed"]
            ),
        },
    }
    embedded = json.dumps(output_data, separators=(",", ":"), sort_keys=True)
    rendered = TEMPLATE.read_text().replace("__SHARED_MULTIPATH_DATA__", embedded)
    if rendered == TEMPLATE.read_text():
        raise RuntimeError("visualization template placeholder was not replaced")
    OUTPUT.write_text(rendered)


if __name__ == "__main__":
    main()
