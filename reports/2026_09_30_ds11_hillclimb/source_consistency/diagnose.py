"""Read-only DS11 source-group inventory and training-only subset feasibility."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sys
import time
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
BASE = HILL.parent / "2026_09_30_ds11_single10"
ENVIRONMENT = HILL.parent / "2026_09_28_full_manifest_inputs" / "environment.json"
SELECTOR = HILL.parent / "2026_09_29_source_consistent_pilot" / "selection.py"
MODULES = (
    "leo.storage.scanner_tracking_source",
    "leo.application.scanner_trajectory",
    "leo.analysis.persistent_hop_trajectory",
)
SCREEN = tuple(range(0, 32, 4))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_selector():
    spec = importlib.util.spec_from_file_location("ds11_source_selector", SELECTOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.select


def selection_summary(rows, select):
    chosen = select(rows)
    ids = set(chosen["track_ids"])
    groups = [group for row in rows if row["track_id"] in ids for group in row["groups"]]
    if len(groups) != len(set(groups)):
        raise ValueError("selected tracks are not source-disjoint")
    total = sum(row["training_count"] for row in rows)
    return {
        "tracks": len(ids),
        "training_observations": chosen["training_count"],
        "training_fraction": chosen["training_count"] / total,
        "alternative_closures": len(chosen["alternatives"]),
        "track_ids": chosen["track_ids"],
    }


def main():
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    environment = json.loads(ENVIRONMENT.read_text())
    module_hashes = {}
    for name in MODULES:
        module = importlib.import_module(name)
        actual = digest(module.__file__)
        if actual != environment["modules"][name]["sha256"]:
            raise ValueError(f"pinned runtime module hash mismatch: {name}")
        module_hashes[name] = actual
    from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
    from leo.application.scanner_trajectory import project_scanner_candidates
    from leo.analysis.persistent_hop_trajectory import (
        PersistentHopTrajectoryConfig,
        reconstruct_persistent_hop_trajectories,
    )

    select = load_selector()
    scans = []
    sidecar_scans = {}
    started = time.monotonic()
    store = ScannerTrackingInputStore(Path("/srv/bulk/leo"))
    try:
        for index in SCREEN:
            entry = plan["inputs"][index]
            observation_path = next(
                Path(row["path"]) for row in entry["artifacts"] if row["kind"] == "observations"
            )
            baseline = json.loads(observation_path.read_text())
            raw = store.load(entry["session_id"])
            if raw.input_manifest_sha256 != baseline["manifest_sha256"]:
                raise ValueError("input manifest does not bind baseline")
            if raw.analysis_manifest_sha256 != baseline["analysis_manifest_sha256"]:
                raise ValueError("analysis manifest does not bind baseline")
            projected = project_scanner_candidates(raw)
            by_candidate = {row.candidate_id: row for row in projected}
            graph = reconstruct_persistent_hop_trajectories(
                projected,
                config=PersistentHopTrajectoryConfig(minimum_span_s=3.0, minimum_support=6),
            )
            tracklets = {row.tracklet_id: row for row in graph.tracklets}
            all_rows = []
            track_sidecar = {}
            for track in baseline["tracks"]:
                source = tracklets[track["track_id"]]
                if len(source.points) != len(track["times_s"]):
                    raise ValueError("source track length differs from baseline")
                points = []
                for point_index, point in enumerate(source.points):
                    candidate = by_candidate[point.candidate_id]
                    time_s = (candidate.support_center_utc_ns - baseline["start_utc_ns"]) / 1e9
                    if abs(time_s - track["times_s"][point_index]) > 1e-9:
                        raise ValueError("source point time differs from baseline")
                    if abs(point.normalized_dealiased_cfo_hz - track["measured_hz"][point_index]) >= 1e-7:
                        raise ValueError("source point frequency differs from baseline")
                    if (candidate.receiver_id != track["receiver_id"]
                            or candidate.channel != track["channel"]
                            or candidate.actual_rf_hz != track["rf_hz"]
                            or candidate.visit_index != track["visits"][point_index]):
                        raise ValueError("source point receiver/RF/visit differs from baseline")
                    points.append({
                        "source_group_id": candidate.source_group_id,
                        "candidate_id": candidate.candidate_id,
                        "training": bool(track["training_mask"][point_index]),
                    })
                groups = [row["source_group_id"] for row in points]
                if len(groups) != len(set(groups)):
                    raise ValueError("one exported track reuses a source group internally")
                track_sidecar[track["track_id"]] = points
                all_rows.extend({"track_id": track["track_id"], **row} for row in points)

            by_group_all = defaultdict(list)
            by_group_training = defaultdict(list)
            for row in all_rows:
                by_group_all[row["source_group_id"]].append(row)
                if row["training"]:
                    by_group_training[row["source_group_id"]].append(row)

            def conflict(group):
                return len({row["track_id"] for row in group}) > 1

            training_conflicts = {
                key: rows for key, rows in by_group_training.items() if conflict(rows)
            }
            all_conflicts = {key: rows for key, rows in by_group_all.items() if conflict(rows)}
            rows_training = []
            rows_all = []
            for track in baseline["tracks"]:
                points = track_sidecar[track["track_id"]]
                training_groups = [row["source_group_id"] for row in points if row["training"]]
                rows_training.append({
                    "track_id": track["track_id"],
                    "groups": training_groups,
                    "training_count": sum(track["training_mask"]),
                })
                rows_all.append({
                    "track_id": track["track_id"],
                    "groups": [row["source_group_id"] for row in points],
                    "training_count": sum(track["training_mask"]),
                })
            selected_training = selection_summary(rows_training, select)
            selected_all = selection_summary(rows_all, select)
            training_conflict_rows = [row for rows in training_conflicts.values() for row in rows]
            scan = {
                "index": index,
                "session_id": entry["session_id"],
                "tracks": len(baseline["tracks"]),
                "observations": len(all_rows),
                "training_observations": sum(row["training"] for row in all_rows),
                "source_groups_all": len(by_group_all),
                "source_groups_training": len(by_group_training),
                "conflicting_source_groups_all": len(all_conflicts),
                "conflicting_source_groups_training": len(training_conflicts),
                "training_observations_in_conflicts": len(training_conflict_rows),
                "tracks_touching_training_conflicts": len({
                    row["track_id"] for row in training_conflict_rows
                }),
                "distinct_candidate_conflicts_training": sum(
                    len({row["candidate_id"] for row in rows}) > 1
                    for rows in training_conflicts.values()
                ),
                "training_only_selection": selected_training,
                "all_point_selection": selected_all,
                "observation_sha256": digest(observation_path),
            }
            scans.append(scan)
            sidecar_scans[str(index)] = {
                "session_id": entry["session_id"],
                "observation_sha256": scan["observation_sha256"],
                "tracks": track_sidecar,
            }
            print(index, scan["tracks"], scan["conflicting_source_groups_training"],
                  selected_training["training_fraction"], flush=True)
    finally:
        store.close()

    totals = {
        "scans": len(scans),
        "tracks": sum(row["tracks"] for row in scans),
        "observations": sum(row["observations"] for row in scans),
        "training_observations": sum(row["training_observations"] for row in scans),
        "conflicting_source_groups_training": sum(
            row["conflicting_source_groups_training"] for row in scans
        ),
        "training_observations_in_conflicts": sum(
            row["training_observations_in_conflicts"] for row in scans
        ),
        "training_only_selected_tracks": sum(
            row["training_only_selection"]["tracks"] for row in scans
        ),
        "training_only_selected_observations": sum(
            row["training_only_selection"]["training_observations"] for row in scans
        ),
        "all_point_selected_tracks": sum(row["all_point_selection"]["tracks"] for row in scans),
        "all_point_selected_training_observations": sum(
            row["all_point_selection"]["training_observations"] for row in scans
        ),
    }
    totals["training_conflict_observation_fraction"] = (
        totals["training_observations_in_conflicts"] / totals["training_observations"]
    )
    totals["training_only_retained_fraction"] = (
        totals["training_only_selected_observations"] / totals["training_observations"]
    )
    totals["all_point_retained_training_fraction"] = (
        totals["all_point_selected_training_observations"] / totals["training_observations"]
    )
    result = {
        "schema": "ds11-source-group-feasibility/v1",
        "scope": "screen8 read-only provenance; training source groups only for primary selector",
        "indices": list(SCREEN),
        "selector": "unchanged seeded greedy maximum training coverage",
        "totals": totals,
        "scans": scans,
        "source_sha256": {
            str(path): digest(path) for path in (
                Path(__file__), plan_path, ENVIRONMENT, SELECTOR,
            )
        },
        "runtime_module_sha256": module_hashes,
        "elapsed_s": time.monotonic() - started,
    }
    sidecar = {
        "schema": "ds11-source-group-sidecar/v1",
        "plan_sha256": digest(plan_path),
        "runtime_module_sha256": module_hashes,
        "scans": sidecar_scans,
    }
    with (HERE / "diagnostic.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    with (HERE / "source_groups.json").open("x") as stream:
        json.dump(sidecar, stream, indent=2, allow_nan=False)
    print(json.dumps(totals, indent=2), flush=True)


if __name__ == "__main__":
    main()
