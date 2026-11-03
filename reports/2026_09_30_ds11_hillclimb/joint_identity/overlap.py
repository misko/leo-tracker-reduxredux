"""Training-only feasibility census for shared physical candidate identity."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from itertools import combinations
from pathlib import Path


HERE = Path(__file__).resolve().parent
HILL = HERE.parent
ROOT = HERE.parents[2]
BASE = HILL.parent / "2026_09_30_ds11_single10"
SOURCE_MODEL = HILL / "source_balance" / "model.py"
SCREEN = tuple(range(0, 32, 4))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_source_model():
    spec = importlib.util.spec_from_file_location("joint_identity_frozen_source", SOURCE_MODEL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    sys.path.insert(0, str(ROOT / "tools"))
    import ds7_fast_baseline_adapter as baseline

    baseline.baseline.profile = baseline.profile
    source = load_source_model()
    plan = json.loads((BASE / "plan.json").read_text())
    sidecar_path = HILL / "source_balance" / "catalogue_identities.json"
    sidecar = json.loads(sidecar_path.read_text())
    scans = []
    totals = {
        "tracks": 0,
        "unambiguous_tracks": 0,
        "ambiguous_tracks": 0,
        "repeated_selected_norads": 0,
        "joint_groups_cross_stratum": 0,
        "joint_group_tracks_cross_stratum": 0,
        "joint_groups_cross_receiver": 0,
        "joint_groups_cross_rf": 0,
        "joint_groups_cross_receiver_and_rf": 0,
        "cross_stratum_pairs": 0,
        "cross_stratum_pairs_with_candidate_intersection": 0,
        "cross_stratum_pairs_same_strong_norad": 0,
    }
    for index in SCREEN:
        entry = plan["inputs"][index]
        documents = baseline.load_documents({"config": plan["config"], "inputs": [entry]})
        incumbent_path = BASE / "runs" / f"{index:02d}_iid.json"
        incumbent = json.loads(incumbent_path.read_text())["selected"]
        assert incumbent is not None
        identity_scan = sidecar["scans"][str(index)]
        candidate_norad = [{
            track_id: row["candidate_norad"]
            for track_id, row in identity_scan["tracks"].items()
        }]
        assignments = source.freeze_assignments(
            documents, plan["config"], incumbent["x"], candidate_norad
        )
        document = documents[0]
        by_selected = {}
        for row in assignments:
            if row["unambiguous"]:
                by_selected.setdefault(row["norad"], []).append(row)

        groups = []
        repeated = {norad: rows for norad, rows in by_selected.items() if len(rows) >= 2}
        for norad, rows in sorted(repeated.items()):
            strata = {(row["receiver_id"], row["rf_hz"]) for row in rows}
            if len(strata) < 2:
                continue
            receivers = {row["receiver_id"] for row in rows}
            frequencies = {row["rf_hz"] for row in rows}
            candidates = [set(candidate_norad[0][row["track_id"]]) for row in rows]
            intersection = set.intersection(*candidates)
            union = set.union(*candidates)
            assert norad in intersection
            groups.append({
                "norad": norad,
                "tracks": len(rows),
                "track_ids": [row["track_id"] for row in rows],
                "receiver_ids": sorted(receivers),
                "rf_hz": sorted(frequencies),
                "strata": len(strata),
                "cross_receiver": len(receivers) >= 2,
                "cross_rf": len(frequencies) >= 2,
                "common_candidate_norads": len(intersection),
                "union_candidate_norads": len(union),
                "common_fraction_of_union": len(intersection) / len(union),
                "minimum_confidence": min(row["confidence"] for row in rows),
            })

        pair_rows = []
        for left, right in combinations(assignments, 2):
            if (left["receiver_id"], left["rf_hz"]) == (right["receiver_id"], right["rf_hz"]):
                continue
            left_ids = set(candidate_norad[0][left["track_id"]])
            right_ids = set(candidate_norad[0][right["track_id"]])
            common = left_ids & right_ids
            same_strong = bool(
                left["unambiguous"] and right["unambiguous"]
                and left["norad"] == right["norad"]
            )
            pair_rows.append((len(common), same_strong))

        row = {
            "index": index,
            "session_id": entry["session_id"],
            "tracks": len(assignments),
            "unambiguous_tracks": sum(item["unambiguous"] for item in assignments),
            "ambiguous_tracks": sum(not item["unambiguous"] for item in assignments),
            "distinct_unambiguous_norads": len(by_selected),
            "repeated_selected_norads": len(repeated),
            "joint_groups_cross_stratum": len(groups),
            "joint_group_tracks_cross_stratum": sum(group["tracks"] for group in groups),
            "joint_groups_cross_receiver": sum(group["cross_receiver"] for group in groups),
            "joint_groups_cross_rf": sum(group["cross_rf"] for group in groups),
            "joint_groups_cross_receiver_and_rf": sum(
                group["cross_receiver"] and group["cross_rf"] for group in groups
            ),
            "cross_stratum_pairs": len(pair_rows),
            "cross_stratum_pairs_with_candidate_intersection": sum(
                count > 0 for count, _ in pair_rows
            ),
            "cross_stratum_pairs_same_strong_norad": sum(
                same for _, same in pair_rows
            ),
            "candidate_intersection_pair_median": None,
            "groups": groups,
        }
        counts = sorted(count for count, _ in pair_rows)
        if counts:
            middle = len(counts) // 2
            row["candidate_intersection_pair_median"] = (
                counts[middle] if len(counts) % 2 else (counts[middle - 1] + counts[middle]) / 2
            )
        scans.append(row)
        for key in totals:
            totals[key] += row[key]

    group_rows = [group for scan in scans for group in scan["groups"]]
    result = {
        "schema": "ds11-joint-identity-overlap/v1",
        "scope": "screen8 original same-scan IID endpoint; training likelihood only",
        "confidence_threshold": source.CONFIDENCE_THRESHOLD,
        "group_feasibility_rule": (
            "same >=0.90 training-selected physical NORAD in at least two exact "
            "(receiver_id, rf_hz) strata"
        ),
        "screen_indices": list(SCREEN),
        "totals": totals,
        "group_size_histogram": {
            str(size): sum(group["tracks"] == size for group in group_rows)
            for size in sorted({group["tracks"] for group in group_rows})
        },
        "common_candidate_count_histogram": {
            str(count): sum(group["common_candidate_norads"] == count for group in group_rows)
            for count in sorted({group["common_candidate_norads"] for group in group_rows})
        },
        "scans": scans,
        "source_sha256": {
            str(path): digest(path)
            for path in (Path(__file__), SOURCE_MODEL, sidecar_path, BASE / "plan.json")
        },
        "incumbent_sha256": {
            str(index): digest(BASE / "runs" / f"{index:02d}_iid.json") for index in SCREEN
        },
    }
    output = HERE / "overlap.json"
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps({
        "totals": totals,
        "group_size_histogram": result["group_size_histogram"],
        "common_candidate_count_histogram": result["common_candidate_count_histogram"],
        "per_scan": [{key: scan[key] for key in (
            "index", "tracks", "unambiguous_tracks", "joint_groups_cross_stratum",
            "joint_group_tracks_cross_stratum", "joint_groups_cross_receiver",
            "joint_groups_cross_rf")}
            for scan in scans],
    }, indent=2))


if __name__ == "__main__":
    main()
