"""Name the existing frozen long-duration cohort DS1; do not repartition it."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / "reports/2026_09_23_long_inventory_complete"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, inventory):
    index = {g["utc_8h_start"]: g for g in inventory["utc_8h_groups"]}
    groups, cases, seen = [], [], set()
    for partition in ("train", "validation", "test"):
        part = source["partitions"][partition]
        members = []
        for start in part["groups"]:
            original = index[start]
            ids = original["session_ids"]
            if len(ids) != len(set(ids)) or seen.intersection(ids):
                raise ValueError("Duplicate or cross-partition recording")
            seen.update(ids)
            members.extend(ids)
            group_id = start[:13].replace("-", "").replace("T", "_")
            groups.append({**original, "group_id": group_id, "partition": partition})
            for view in (1, 6, 16, "all"):
                count = len(ids) if view == "all" else view
                if count > len(ids):
                    raise ValueError("Insufficient scans for predefined view")
                cases.append({
                    "case_id": f"{partition}_{group_id}_{view}",
                    "group_id": group_id, "partition": partition,
                    "view": str(view), "scan_count": count,
                    "session_ids": ids[:count],
                })
        if members != part["session_ids"]:
            raise ValueError("Original membership/order changed")
    return {
        "schema": "ds1-benchmark/v1", "name": "DS1", "version": 1,
        "scope": "Existing frozen cohort; retrospective regression benchmark",
        "exposure": "TRAIN developed on; validation and partial TEST previously evaluated",
        "group_hours": 8, "groups": groups, "cases": cases,
        "priors": {"sacramento": [38.5816, -121.4944, 250.0],
                   "reno": [39.5296, -119.8138, 500.0]},
        "partition_counts": {p: len(source["partitions"][p]["session_ids"])
                             for p in ("train", "validation", "test")},
        "views_are_nested_not_independent": True,
        "duration_note": "Eight-hour calendar groups have gaps; not continuous IQ",
    }


def main():
    source = SOURCE / "manifest.json"
    inventory = SOURCE / "inventory.json"
    if digest(source) != (SOURCE / "manifest.sha256").read_text().strip():
        raise ValueError("Original cohort seal mismatch")
    result = build(json.loads(source.read_text()), json.loads(inventory.read_text()))
    result["bindings"] = {
        "original_manifest": digest(source), "original_inventory": digest(inventory),
        "generator": digest(Path(__file__)),
    }
    path = HERE / "dataset.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    path.with_suffix(".sha256").write_text(digest(path) + "\n")
    print(json.dumps({"counts": result["partition_counts"],
                      "cases": len(result["cases"]), "seal": digest(path)}))


if __name__ == "__main__":
    main()
