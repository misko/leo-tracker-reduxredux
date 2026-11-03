"""Freeze matched single/pair/quad cohorts using acquisition metadata only."""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SEED = 2026100217
MAX_IDLE_S = 180.0
MANIFESTS = {
    "DS10": ROOT.parent / "2026_09_29_ds10_post_ds9/local/manifest.json",
    "DS11": ROOT.parent / "2026_09_30_ds11_post_ds10/local/manifest.json",
}


def eligible_windows(manifest):
    admitted = manifest["captures"]
    inventory = [*admitted, *manifest.get("excluded", [])]
    identifiers = [row["session_id"] for row in inventory]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate capture identity in admitted/excluded inventory")
    if any(row.get("capture_start_utc_ns") is None for row in inventory):
        raise ValueError("Cannot prove adjacency with missing inventory timestamps")
    inventory.sort(key=lambda row: (row["capture_start_utc_ns"], row["session_id"]))
    included = {row["session_id"] for row in admitted}
    windows = []
    for start in range(len(inventory) - 3):
        window = inventory[start : start + 4]
        if any(row["session_id"] not in included for row in window):
            continue
        if any(
            not row.get("utc_qualified")
            or sorted(row["receiver_ids"]) != [0, 1]
            or row.get("capture_end_utc_ns", 0) <= row["capture_start_utc_ns"]
            for row in window
        ):
            continue
        if len({row["radio_id"] for row in window}) != 1:
            continue
        gaps = [
            (following["capture_start_utc_ns"] - previous["capture_end_utc_ns"]) / 1e9
            for previous, following in zip(window[:-1], window[1:], strict=True)
        ]
        if any(gap < 0 or gap > MAX_IDLE_S for gap in gaps):
            continue
        windows.append(window)
    return windows


def select_dataset(manifest, seed):
    candidates = eligible_windows(manifest)
    order = list(range(len(candidates)))
    random.Random(seed).shuffle(order)
    selected_windows = []
    used = set()
    for index in order:
        window = candidates[index]
        members = {row["session_id"] for row in window}
        if used & members:
            continue
        selected_windows.append(window)
        used.update(members)
        if len(selected_windows) == 4:
            break
    if len(selected_windows) != 4:
        raise ValueError("Could not select four disjoint eligible consecutive quads")
    selected_windows.sort(key=lambda window: window[0]["capture_start_utc_ns"])
    units = []
    counters = {1: 0, 2: 0, 4: 0}
    dataset = manifest["dataset_id"]
    for block_index, window in enumerate(selected_windows):
        for size, prefix in ((1, "S"), (2, "D"), (4, "Q")):
            for start in range(0, 4, size):
                members = window[start : start + size]
                counters[size] += 1
                origin = members[0]["capture_start_utc_ns"]
                end = members[-1]["capture_end_utc_ns"]
                units.append(
                    {
                        "unit_id": f"{dataset}-{prefix}{counters[size]:02d}",
                        "size": size,
                        "quad_block": block_index + 1,
                        "session_ids": [row["session_id"] for row in members],
                        "origin_utc_ns": origin,
                        "end_utc_ns": end,
                        "elapsed_span_s": (end - origin) / 1e9,
                        "capture_time_offsets_s": [
                            (row["capture_start_utc_ns"] - origin) / 1e9 for row in members
                        ],
                        "idle_gaps_s": [
                            (right["capture_start_utc_ns"] - left["capture_end_utc_ns"]) / 1e9
                            for left, right in zip(members[:-1], members[1:], strict=True)
                        ],
                    }
                )
    return {
        "seed": seed,
        "population_captures": len(manifest["captures"]),
        "eligible_quad_windows": len(candidates),
        "selected": [row["session_id"] for window in selected_windows for row in window],
        "counts": {"single": counters[1], "double": counters[2], "quad": counters[4]},
        "units": units,
    }


def build_selection():
    datasets = {}
    for index, (dataset, path) in enumerate(MANIFESTS.items()):
        payload = path.read_bytes()
        manifest = json.loads(payload)
        if manifest["dataset_id"] != dataset:
            raise ValueError("Dataset identity mismatch")
        selected = select_dataset(manifest, SEED + index)
        selected.update(
            manifest_path=str(path), manifest_sha256=hashlib.sha256(payload).hexdigest()
        )
        datasets[dataset] = selected
    return {
        "schema": "multiscan-localization-selection/v1",
        "datasets": datasets,
        "interpretation": "16 singles, 8 adjacent pairs, 4 adjacent quads PER dataset; "
        "32 distinct captures and 56 fitting units total",
        "selection_policy": "Shuffle metadata-eligible consecutive four-capture windows; "
        "take first four disjoint windows. No error, signal quality, "
        "or reference-location filtering. Failures never replaced.",
        "adjacency": "Consecutive in admitted+excluded capture inventory; same radio, both RXs, "
        "qualified UTC, no overlap, idle gap <=180 s. Real UTC gaps retained.",
        "maximum_idle_gap_s": MAX_IDLE_S,
        "training": "All observations available to each unit; no within-unit heldout partition",
        "reset": "Each fitting unit starts from the geographic prior; no fitted nuisance/position "
        "state transferred between units or datasets",
        "dependence": "Single/double/quad cases deliberately share captures; compare paired "
        "outcomes and do not treat 56 units as independent trials",
        "success_reporting": "Report every single-scan error and failure, median, p90, maximum, "
        "and fraction below 1 km; do not substitute the best scan for "
        "single-scan accuracy",
    }


def main():
    selection = build_selection()
    destination = ROOT / "selection.json"
    if destination.exists():
        if json.loads(destination.read_text()) != selection:
            raise ValueError("Refusing to change frozen selection")
    else:
        destination.write_text(json.dumps(selection, indent=2) + "\n")
    print(
        json.dumps(
            {
                dataset: {
                    key: value[key]
                    for key in ("population_captures", "eligible_quad_windows", "counts")
                }
                for dataset, value in selection["datasets"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
