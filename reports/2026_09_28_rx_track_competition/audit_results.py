"""Independently recompute track-competition support and aggregation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROLES = ("reception", "held_frequency")
RECEIVERS = ("rx0", "rx1")
THRESHOLDS = (500, 1500)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right) -> None:
    if isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left:
            close(left[key], right[key])
    elif isinstance(left, float):
        assert math.isclose(left, float(right), rel_tol=0, abs_tol=1e-12)
    else:
        assert left == right


def lane_key(row: dict) -> tuple:
    return row["session_id"], int(row["channel"]), row["edge"], float(row["actual_rf_hz"])


def mean(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    names = rows[0]["metrics"]
    return {
        "windows": len(rows),
        "metrics": {n: math.fsum(r["metrics"][n] for r in rows) / len(rows) for n in names},
    }


def recompute(dataset: dict, mapping: dict, result: dict) -> tuple[dict, dict]:
    mapped: dict[tuple, list[dict]] = defaultdict(list)
    for track in mapping["tracks"]:
        mapped[lane_key(track)].append(track)
    output_lanes = {lane_key(row["lane"]): row for row in result["lanes"]}
    record_rows: dict[str, list[dict]] = defaultdict(list)
    record_splits = {}
    distinct_candidate_overlap = distinct_observation_overlap = shared_overlap = 0
    exported_shared = exported_distinct_observation = 0
    ages = []
    for lane in dataset["lanes"]:
        key = lane_key(lane["lane"])
        exported = output_lanes[key]
        tracks = mapped[key]
        nominees = lane["components"][:-1]
        logs = [
            float(n["log_prior"]) if n["log_prior"] is not None else -math.inf for n in nominees
        ]
        peak = max(logs)
        raw = [math.exp(value - peak) for value in logs]
        frozen = [value / math.fsum(raw) for value in raw]
        indices = {
            track_id: [i for i, n in enumerate(nominees) if n["track_id"] == track_id]
            for track_id in {n["track_id"] for n in nominees}
        }
        conditional = {}
        support_end = {}
        for track_id, idx in indices.items():
            values = [raw[i] for i in idx]
            conditional[track_id] = [value / math.fsum(values) for value in values]
            support_end[track_id] = max(
                point["support_center_utc_ns"]
                for t in tracks
                if t["track_id"] == track_id
                for point in t["training_alias_points"]
            )
        # Independently count simultaneous same-window track support on each receiver.
        by_receiver = defaultdict(list)
        for track in tracks:
            windows = defaultdict(lambda: (set(), set()))
            for point in track["training_alias_points"]:
                candidates, observations = windows[point["source_window_id"]]
                candidates.add(point["candidate_id"])
                observations.add(point["observation_id"])
            by_receiver[int(track["receiver_id"])].append((track["track_id"], windows))
        for rows in by_receiver.values():
            for (_, left), (_, right) in combinations(rows, 2):
                for wid in set(left) & set(right):
                    shared_overlap += 1
                    distinct_candidate_overlap += left[wid][0].isdisjoint(right[wid][0])
                    distinct_observation_overlap += left[wid][1].isdisjoint(right[wid][1])
        for pair in exported["prefix_track_pair_overlaps"]:
            exported_shared += pair["shared_source_windows"]
            exported_distinct_observation += pair["distinct_observation_overlap_windows"]
        assert exported_shared == shared_overlap
        assert exported_distinct_observation == distinct_observation_overlap
        exported_windows = {row["source_window_id"]: row for row in exported["windows"]}
        period = float(lane["alias_period_hz"])
        for window in lane["windows"]:
            compatible = []
            for prediction in window["predictions"]:
                row = {}
                for receiver in RECEIVERS:
                    residual = min(
                        (
                            abs(
                                (
                                    float(c["canonical_rx0_hz"])
                                    - float(prediction["mu_canonical_rx0_hz"])
                                    + period / 2
                                )
                                % period
                                - period / 2
                            )
                            for c in window["observed"][receiver]
                        ),
                        default=math.inf,
                    )
                    row[receiver] = {
                        threshold: bool(prediction["visible"] and residual <= threshold)
                        for threshold in THRESHOLDS
                    }
                compatible.append(row)
            metrics = {}
            track_rows = {}
            for track_id, idx in indices.items():
                track_rows[track_id] = {
                    f"{receiver}_within_{threshold}hz": math.fsum(
                        weight * compatible[i][receiver][threshold]
                        for i, weight in zip(idx, conditional[track_id], strict=True)
                    )
                    for receiver in RECEIVERS
                    for threshold in THRESHOLDS
                }
                age = (window["prediction_utc_ns"] - support_end[track_id]) / 1e9
                track_rows[track_id]["forecast_age_s"] = age
                ages.append(age)
            for receiver in RECEIVERS:
                for threshold in THRESHOLDS:
                    suffix = f"{receiver}_within_{threshold}hz"
                    metrics[f"frozen_prior_weighted_{suffix}"] = math.fsum(
                        weight * compatible[i][receiver][threshold]
                        for i, weight in enumerate(frozen)
                    )
                    metrics[f"optimistic_track_conditional_max_{suffix}"] = max(
                        r[suffix] for r in track_rows.values()
                    )
                    metrics[f"any_nominee_ceiling_{suffix}"] = float(
                        any(r[receiver][threshold] for r in compatible)
                    )
            actual = exported_windows[window["source_window_id"]]
            close(metrics, actual["metrics"])
            close(track_rows, actual["tracks"])
            record_rows[key[0]].append({"role": window["role"], "metrics": metrics})
        record_splits[key[0]] = lane["recording_split"]
    records = {
        sid: {
            "recording_split": record_splits[sid],
            "roles": {role: mean([r for r in rows if r["role"] == role]) for role in ROLES},
        }
        for sid, rows in record_rows.items()
    }
    by_split = {}
    for split in sorted(set(record_splits.values())):
        by_split[split] = {}
        for role in ROLES:
            rows = [
                row["roles"][role]
                for row in records.values()
                if row["recording_split"] == split and row["roles"][role]
            ]
            if rows:
                names = rows[0]["metrics"]
                by_split[split][role] = {
                    "records": len(rows),
                    "windows": sum(r["windows"] for r in rows),
                    "metrics": {
                        n: math.fsum(r["metrics"][n] for r in rows) / len(rows) for n in names
                    },
                }
    close(records, result["records"])
    close(by_split, result["aggregate_equal_record_by_split"])
    assert min(ages) > 0
    return {
        "recordings": len(records),
        "windows": sum(len(v) for v in record_rows.values()),
        "shared_track_support_windows": shared_overlap,
        "distinct_candidate_overlap_windows": distinct_candidate_overlap,
        "distinct_observation_overlap_windows": distinct_observation_overlap,
        "forecast_age_s_min": min(ages),
        "forecast_age_s_max": max(ages),
    }, by_split


def main() -> None:
    parser = argparse.ArgumentParser()
    for panel in ("pilot", "ds8"):
        for kind in ("results", "dataset", "mapping"):
            parser.add_argument(f"--{panel}-{kind}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    checks = {}
    sources = {}
    for panel in ("pilot", "ds8"):
        paths = {
            kind: getattr(args, f"{panel}_{kind}") for kind in ("results", "dataset", "mapping")
        }
        result, dataset, mapping = (
            json.loads(paths[k].read_text()) for k in ("results", "dataset", "mapping")
        )
        assert result["source_sha256"] == {
            "dataset": digest(paths["dataset"]),
            "mapping": digest(paths["mapping"]),
        }
        assert dataset["source_digests"]["mapping"] == "sha256:" + digest(paths["mapping"])
        checks[panel], _ = recompute(dataset, mapping, result)
        sources[panel] = {kind: digest(path) for kind, path in paths.items()}
    args.output.write_text(
        json.dumps(
            {
                "schema": "rx-track-competition-audit/v1",
                "status": "passed",
                "source_sha256": sources,
                "checks": checks,
                "semantics": (
                    "Track-conditional maxima and any-nominee values are optimistic "
                    "outcome-selected ceilings, not predictive scores."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
