from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SOURCE = (
    HERE
    / "115401-multipath-replay/replay-wide-fine-delay-minus2-to-plus2-step-0p1s.json"
)
TEMPLATE = HERE / "115401-four-path-starlink-candidate.template.html"
OUTPUT = HERE / "115401-four-path-starlink-candidate.html"

PATH_METADATA = {
    "radio_pluto_5d4d:rx0:stream-0:tuning:stream-0:ch2:lower": {
        "label": "5d4d RX0 · lower band",
        "short": "5d RX0",
        "rf_hz": 10_959_687_498.0,
        "input": HERE / "115401-multipath-replay/duration-input-5d4d-rx0.json",
        "branch_id": "sha256:271ebe3092e93f3a4b23f2f425097cf10d1af727da5628b62b6e6648579be5db",
    },
    "radio_pluto_5d4d:rx1:stream-0:tuning:stream-0:ch2:lower": {
        "label": "5d4d RX1 · lower band",
        "short": "5d RX1",
        "rf_hz": 10_959_687_498.0,
        "input": HERE / "115401-multipath-replay/duration-input-5d4d-rx1.json",
        "branch_id": "sha256:2d68f45b4def7a56ba02c532852a04cacc566c0d4ff4748401cb2a82a08df140",
    },
    "radio_pluto_19f2:rx0:stream-1:tuning:stream-1:ch2:upper": {
        "label": "19f2 RX0 · upper band",
        "short": "19f RX0",
        "rf_hz": 11_190_312_500.0,
        "input": HERE / "115401-multipath-replay/duration-input-19f2-rx0.json",
        "branch_id": "sha256:88a3899a568da085dff3fb0f3e312abde315df6e9d5e24badfff0501f988201e",
    },
    "radio_pluto_19f2:rx1:stream-1:tuning:stream-1:ch2:upper": {
        "label": "19f2 RX1 · upper band",
        "short": "19f RX1",
        "rf_hz": 11_190_312_500.0,
        "input": HERE / "115401-multipath-replay/duration-input-19f2-rx1.json",
        "branch_id": "sha256:b1fb41592daf9551d0012970fcf8534c0a1ae0a43a6962cd49e7f06881bc93ec",
    },
}


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _best_state(catalog: dict[str, Any]) -> dict[str, Any]:
    return min(catalog["states"], key=lambda row: float(row["single_satellite_delta_from_null"]))


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    selected = next(row for row in source["association"]["satellites"] if row["selected"])
    hypothesis_id = selected["hypothesis_id"]
    details = source["selected_path_assignment_details"][hypothesis_id]["paths"]
    path_objectives = {
        row["path_id"]: row for row in source["path_full_persisted_inventory_objectives"]
    }
    start_ns = int(source["window"]["start_utc_ns"])
    end_ns = int(source["window"]["end_utc_ns"])
    duration_s = (end_ns - start_ns) / 1e9
    cell_count = int(source["window"]["cell_count"])
    reference_rf_hz = 10_959_687_498.0

    selected_path_by_id = {row["path_id"]: row for row in selected["paths"]}
    paths = []
    reference_doppler_hz: float | None = None
    provisional_rows: dict[str, list[dict[str, Any]]] = {}
    for path_id, metadata in PATH_METADATA.items():
        path_result = selected_path_by_id[path_id]
        assignments = sorted(
            details[path_id]["assignments"],
            key=lambda row: (int(row["estimate_utc_ns"]), str(row["observation_id"])),
        )
        scale = reference_rf_hz / float(metadata["rf_hz"])
        rows = []
        for row in assignments:
            rows.append(
                {
                    "x": (int(row["estimate_utc_ns"]) - start_ns) / 1e9,
                    "observed_deoffset_scaled": (
                        float(row["observed_cfo_hz"])
                        - float(path_result["cfo_offset_hz"])
                    )
                    * scale,
                    "tle_scaled": float(row["geometric_doppler_hz"]) * scale,
                    "residual": float(row["residual_hz"]),
                    "margin": float(row["glrt64_margin"]),
                    "rank": int(row["candidate_rank"]),
                }
            )
        provisional_rows[path_id] = rows
        if path_id.startswith("radio_pluto_5d4d:rx1"):
            first, second = rows[0], rows[1]
            fraction = (0.0 - first["x"]) / (second["x"] - first["x"])
            reference_doppler_hz = first["tle_scaled"] + fraction * (
                second["tle_scaled"] - first["tle_scaled"]
            )

    if reference_doppler_hz is None:
        raise RuntimeError("reference Doppler path was not available")

    for path_index, (path_id, metadata) in enumerate(PATH_METADATA.items()):
        dataset = json.loads(Path(metadata["input"]).read_text(encoding="utf-8"))
        branch = next(
            row for row in dataset["branches"] if row["branch_id"] == metadata["branch_id"]
        )
        path_result = selected_path_by_id[path_id]
        points = [
            [
                round(row["x"], 6),
                round(row["observed_deoffset_scaled"] - reference_doppler_hz, 3),
                round(row["tle_scaled"] - reference_doppler_hz, 3),
                round(row["residual"], 3),
                round(row["margin"], 5),
                row["rank"],
            ]
            for row in provisional_rows[path_id]
        ]
        rms = math.sqrt(sum(row[3] ** 2 for row in points) / len(points))
        cell_assignments = [0] * cell_count
        for row in points:
            cell = max(0, min(cell_count - 1, int(math.floor(row[0] / 0.1))))
            cell_assignments[cell] += 1
        first_utc_ns = int(dataset["timing_binding"]["first_estimate_utc_ns"])
        pilots = []
        for window in branch["frame_coherence_evidence"]["qualified_windows"]:
            pilot_start = (
                first_utc_ns + round(float(window["start_time_s"]) * 1e9) - start_ns
            ) / 1e9
            pilot_end = (
                first_utc_ns + round(float(window["end_time_s"]) * 1e9) - start_ns
            ) / 1e9
            if pilot_end > 0.0 and pilot_start < duration_s:
                pilots.append(
                    [round(max(0.0, pilot_start), 6), round(min(duration_s, pilot_end), 6)]
                )
        paths.append(
            {
                "id": path_id,
                "label": metadata["label"],
                "short": metadata["short"],
                "series": path_index,
                "rf_ghz": round(float(metadata["rf_hz"]) / 1e9, 6),
                "cfo_offset_hz": round(float(path_result["cfo_offset_hz"]), 3),
                "assignments": len(points),
                "misses": len(path_result["missed_probe_ids"]),
                "residual_rms_hz": round(rms, 3),
                "delta_from_null": round(float(path_objectives[path_id]["delta_from_null"]), 6),
                "points": points,
                "cell_assignments": cell_assignments,
                "qualified_pilots": pilots,
                "pilot_qualified_count": int(
                    branch["frame_coherence_evidence"]["deduplicated_qualified_window_count"]
                ),
                "pilot_analyzed_count": int(
                    branch["frame_coherence_evidence"]["deduplicated_analyzed_window_count"]
                ),
            }
        )

    candidates = []
    for catalog in source["nuisance_state_search"]["catalogs"]:
        best = _best_state(catalog)
        candidates.append(
            {
                "catalog_number": int(catalog["catalog_number"]),
                "name": str(best["object_name"]),
                "delay_s": round(float(best["delay_s"]), 3),
                "delta": round(float(best["single_satellite_delta_from_null"]), 6),
                "boundary": bool(
                    best["delay_at_lower_grid_boundary"] or best["delay_at_upper_grid_boundary"]
                ),
                "selected": int(catalog["catalog_number"])
                in source["decision"]["selected_catalog_numbers"],
            }
        )
    candidates.sort(key=lambda row: row["delta"])

    objective = source["decision"]["full_persisted_inventory_objective"]
    data = {
        "capture": "115401",
        "candidate": {
            "catalog_number": int(selected["catalog_number"]),
            "name": str(selected["object_name"]),
            "delay_s": float(selected["delay_s"]),
        },
        "window_duration_s": duration_s,
        "cell_count": cell_count,
        "minimum_active_duration_s": float(source["window"]["minimum_active_duration_s"]),
        "episodes": [
            [
                float(row["start_cell"]) * float(source["window"]["cell_duration_s"]),
                float(row["end_cell_exclusive"])
                * float(source["window"]["cell_duration_s"]),
            ]
            for row in selected["episodes"]
        ],
        "paths": paths,
        "candidates": candidates,
        "wrong_time": [
            {"path": "5d RX0", "actual": -1545.3381, "minus30": -224.9760},
            {"path": "19f RX0", "actual": -336.7012, "minus30": -118.5405},
        ],
        "objective": {
            "null": round(float(objective["null_cost"]), 6),
            "total": round(float(objective["total_cost"]), 6),
            "delta": round(float(objective["delta_from_null"]), 6),
        },
        "search": {
            "eligible_catalogs_independent_screen": 447,
            "explicit_joint_shortlist_count": 3,
            "generated_states_per_catalog": 656,
            "retained_states_per_catalog": 4,
            "joint_combinations_evaluated": 64,
            "joint_combinations_possible": 64,
            "fixed_decisions_exact": True,
            "catalogue_search_exact": False,
        },
        "claims": {
            "candidate_only": True,
            "specificity_claimed": False,
            "payload_decoded": False,
            "structural_costs_calibrated": False,
            "episode_touches_both_window_edges": True,
            "all_probes_at_candidate_cap": True,
            "delay_is_grid_point_not_precise_estimate": True,
            "wrong_time_values_not_bound_into_joint_replay": True,
            "physical_alias_groups_not_exhaustive": True,
        },
        "provenance": {
            "source_digest": _digest(SOURCE),
            "search_configuration_digest": source["search_configuration_digest"],
            "score_calibration_digest": source["input"]["score_calibration_digest"],
            "tle_digest": source["input"]["tle_digest"],
        },
    }
    embedded = json.dumps(data, separators=(",", ":"), sort_keys=True)
    template = TEMPLATE.read_text(encoding="utf-8")
    rendered = template.replace("__DWELL_115401_DATA__", embedded)
    if rendered == template:
        raise RuntimeError("visualization data placeholder was not replaced")
    OUTPUT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
