"""Build leakage-resistant partitions from recorded RX opportunity metadata.

This tool assigns no satellite identity and performs no scientific fitting.  It
uses only recording identity, timestamps, receiver identity, sample rate, and
projected source support carried by the opportunity export.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROLES = ("train", "reception", "held_frequency", "embargo")
RECORDING_SPLIT_SEED = "20260928:rx-training-forecast:"
EVALUATION_QUOTAS = {10_000_000: 2, 2_500_000: 1, 5_000_000: 1, 7_500_000: 0}


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _receiver_ids(row: dict[str, Any]) -> list[int]:
    receivers = row.get("receivers")
    if not isinstance(receivers, dict):
        raise ValueError("opportunity receivers must be an object")
    result = []
    for name, view in receivers.items():
        if not isinstance(view, dict):
            raise ValueError("receiver view must be an object")
        value = view.get("receiver_id")
        if value is None and name in {"rx0", "rx1"}:
            value = int(name[-1])
        result.append(_integer(value, "receiver_id"))
    if sorted(result) != [0, 1]:
        raise ValueError("each source window must keep exactly receivers 0 and 1 together")
    return sorted(result)


def _source_intervals(row: dict[str, Any]) -> list[tuple[str, str, int, int]]:
    """Read source-support metadata without consulting any detection outcome."""
    intervals: set[tuple[str, str, int, int]] = set()
    receivers = row["receivers"]
    for view in receivers.values():
        receiver_id = _integer(view.get("receiver_id"), "receiver_id")
        expected_stream = f"rx-{receiver_id}"
        candidates = view.get("candidates", [])
        if not isinstance(candidates, list):
            raise ValueError("receiver candidates must be a list")
        for candidate in candidates:
            support = candidate.get("source_interval")
            if support is None:
                continue
            if not isinstance(support, dict):
                raise ValueError("candidate source_interval must be an object or null")
            group = support.get("source_group_id")
            if not isinstance(group, str) or not group:
                raise ValueError("source interval requires source_group_id")
            stream = support.get("stream_id")
            if stream is not None and not isinstance(stream, str):
                raise ValueError("source interval stream_id must be a string or null")
            if stream is not None and stream != expected_stream:
                raise ValueError("source interval stream_id disagrees with its receiver view")
            stream = expected_stream
            start = _integer(support.get("source_sample_start"), "source_sample_start")
            end = _integer(support.get("source_sample_end"), "source_sample_end")
            if start >= end:
                raise ValueError("source sample interval must be non-empty")
            intervals.add((group, stream, start, end))
    return sorted(intervals)


def _normalized_window(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("schema") != "rx-paired-opportunity/v1":
        raise ValueError("input row is not rx-paired-opportunity/v1")
    source = row.get("source_window")
    if not isinstance(source, dict):
        raise ValueError("opportunity source_window must be an object")
    session = source.get("session_id")
    window_id = row.get("source_window_id")
    if not isinstance(session, str) or not session or not isinstance(window_id, str):
        raise ValueError("opportunity requires session_id and source_window_id")
    start = _integer(row.get("window_start_utc_ns"), "window_start_utc_ns")
    end = _integer(row.get("window_end_utc_ns"), "window_end_utc_ns")
    rate = _integer(source.get("sample_rate_hz"), "sample_rate_hz")
    if start >= end or rate <= 0:
        raise ValueError("opportunity time interval and sample rate must be positive")
    receivers = row["receivers"]
    return {
        "source_window_id": window_id,
        "session_id": session,
        "sample_rate_hz": rate,
        "window_start_utc_ns": start,
        "window_end_utc_ns": end,
        "receiver_ids": _receiver_ids(row),
        "source_intervals": _source_intervals(row),
        "visit_index": _integer(source.get("visit_index"), "visit_index"),
        "probe_index": _integer(source.get("probe_index"), "probe_index"),
        "probe_start_ms": _integer(source.get("probe_start_ms"), "probe_start_ms"),
        "channel": _integer(source.get("channel"), "channel"),
        "edge": source.get("edge"),
        "actual_rf_hz_by_receiver": {
            name: view.get("actual_rf_hz") for name, view in sorted(receivers.items())
        },
    }


def _join_overlaps(windows: list[dict[str, Any]]) -> _UnionFind:
    union = _UnionFind(len(windows))
    by_session: dict[str, list[int]] = defaultdict(list)
    source_support: dict[tuple[str, str], list[tuple[int, int, int]]] = defaultdict(list)
    for index, window in enumerate(windows):
        by_session[window["session_id"]].append(index)
        for _group, stream, start, end in window["source_intervals"]:
            # Group IDs describe projected probes, while sample coordinates can
            # expose shared payload support across those IDs and across tracks.
            source_support[(window["session_id"], stream)].append((start, end, index))

    # A sweep against the furthest-reaching active interval captures transitive
    # overlap while avoiding a quadratic all-pairs comparison.
    for indices in by_session.values():
        ordered = sorted(indices, key=lambda i: (windows[i]["window_start_utc_ns"], i))
        active_index, active_end = ordered[0], windows[ordered[0]]["window_end_utc_ns"]
        for index in ordered[1:]:
            start, end = windows[index]["window_start_utc_ns"], windows[index]["window_end_utc_ns"]
            if start < active_end:
                union.union(active_index, index)
            if end > active_end:
                active_index, active_end = index, end
    for intervals in source_support.values():
        ordered = sorted(intervals)
        active_start, active_end, active_index = ordered[0]
        del active_start
        for start, end, index in ordered[1:]:
            if start < active_end:
                union.union(active_index, index)
            if end > active_end:
                active_end, active_index = end, index
    return union


def _recording_splits(windows: list[dict[str, Any]]) -> dict[str, str]:
    rates: dict[int, list[str]] = defaultdict(list)
    session_rates: dict[str, set[int]] = defaultdict(set)
    for window in windows:
        session_rates[window["session_id"]].add(window["sample_rate_hz"])
    if any(len(values) != 1 for values in session_rates.values()):
        raise ValueError("one session cannot contain multiple sample rates")
    for session, values in session_rates.items():
        rates[next(iter(values))].append(session)

    def key(value: str) -> tuple[str, str]:
        return (
            hashlib.sha256((RECORDING_SPLIT_SEED + value).encode()).hexdigest(),
            value,
        )

    sessions = sorted(session_rates, key=key)
    evaluation: set[str] = set()
    if set(rates) != set(EVALUATION_QUOTAS):
        raise ValueError("recording inventory does not contain the frozen sample-rate panel")
    for rate, quota in EVALUATION_QUOTAS.items():
        members = sorted(rates[rate], key=key)
        if len(members) <= quota:
            raise ValueError(f"sample rate {rate} lacks calibration support after evaluation quota")
        evaluation.update(members[:quota])
    if len(sessions) != 10 or len(evaluation) != 4:
        raise ValueError(
            "frozen recording split requires exactly ten recordings and four evaluations"
        )
    result = {
        session: ("evaluation" if session in evaluation else "calibration") for session in sessions
    }
    for rate, members in rates.items():
        roles = {result[session] for session in members}
        if len(members) == 1 and result[members[0]] != "calibration":
            raise AssertionError("singleton sample rate escaped calibration")
        if len(members) >= 2 and roles != {"calibration", "evaluation"}:
            raise ValueError(f"sample rate {rate} lacks calibration/evaluation coverage")
    return result


def build_partition(
    rows: Iterable[dict[str, Any]], *, evaluation_only: bool = False
) -> dict[str, Any]:
    windows = [_normalized_window(row) for row in rows]
    if not windows:
        raise ValueError("opportunity input is empty")
    ids = [window["source_window_id"] for window in windows]
    if len(ids) != len(set(ids)):
        raise ValueError("source_window_id values must be unique")
    windows.sort(
        key=lambda item: (item["session_id"], item["window_start_utc_ns"], item["source_window_id"])
    )
    union = _join_overlaps(windows)
    members: dict[int, list[int]] = defaultdict(list)
    for index in range(len(windows)):
        members[union.find(index)].append(index)
    recording_splits = (
        {window["session_id"]: "evaluation" for window in windows}
        if evaluation_only
        else _recording_splits(windows)
    )

    spans: dict[str, tuple[int, int, int, int]] = {}
    for session in sorted({window["session_id"] for window in windows}):
        selected = [window for window in windows if window["session_id"] == session]
        start = min(item["window_start_utc_ns"] for item in selected)
        end = max(item["window_end_utc_ns"] for item in selected)
        duration = end - start
        spans[session] = (start, end, start + duration * 3 // 5, start + duration * 4 // 5)

    groups = []
    role_by_window: dict[str, tuple[str, str]] = {}
    for indices in sorted(
        members.values(), key=lambda values: min(windows[i]["source_window_id"] for i in values)
    ):
        session_values = {windows[index]["session_id"] for index in indices}
        if len(session_values) != 1:
            raise AssertionError("connected group crossed sessions")
        session = next(iter(session_values))
        start = min(windows[index]["window_start_utc_ns"] for index in indices)
        end = max(windows[index]["window_end_utc_ns"] for index in indices)
        _, _, training_end, reception_end = spans[session]
        role = (
            "train"
            if end <= training_end
            else "reception"
            if start >= training_end and end <= reception_end
            else "held_frequency"
            if start >= reception_end
            else "embargo"
        )
        window_ids = sorted(windows[index]["source_window_id"] for index in indices)
        digest = hashlib.sha256("\n".join(window_ids).encode()).hexdigest()
        group_id = f"rx-connected-window-group/v1:sha256:{digest}"
        for window_id in window_ids:
            role_by_window[window_id] = (group_id, role)
        groups.append(
            {
                "group_id": group_id,
                "session_id": session,
                "window_start_utc_ns": start,
                "window_end_utc_ns": end,
                "role": role,
                "window_ids": window_ids,
            }
        )

    output_windows = []
    for window in windows:
        group_id, role = role_by_window[window["source_window_id"]]
        output_windows.append(
            {
                "source_window_id": window["source_window_id"],
                "session_id": window["session_id"],
                "sample_rate_hz": window["sample_rate_hz"],
                "recording_split": recording_splits[window["session_id"]],
                "group_id": group_id,
                "role": role,
                "receiver_ids": window["receiver_ids"],
                "window_start_utc_ns": window["window_start_utc_ns"],
                "window_end_utc_ns": window["window_end_utc_ns"],
                "window_midpoint_utc_ns": (
                    window["window_start_utc_ns"] + window["window_end_utc_ns"]
                )
                // 2,
                "visit_index": window["visit_index"],
                "probe_index": window["probe_index"],
                "probe_start_ms": window["probe_start_ms"],
                "channel": window["channel"],
                "edge": window["edge"],
                "actual_rf_hz_by_receiver": window["actual_rf_hz_by_receiver"],
            }
        )
    recordings = []
    for session, (start, end, training_end, reception_end) in sorted(spans.items()):
        rate = next(
            window["sample_rate_hz"] for window in windows if window["session_id"] == session
        )
        recordings.append(
            {
                "session_id": session,
                "sample_rate_hz": rate,
                "recording_split": recording_splits[session],
                "first_window_start_utc_ns": start,
                "last_window_end_utc_ns": end,
                "training_end_utc_ns": training_end,
                "reception_end_utc_ns": reception_end,
            }
        )
    role_counts = Counter(item["role"] for item in output_windows)
    split_counts = Counter(item["recording_split"] for item in recordings)
    return {
        "schema": "rx-grouped-partition/v1",
        "policy": {
            "time_support_fractions": {"train": 0.6, "reception": 0.2, "held_frequency": 0.2},
            "boundary_crossing_group_role": "embargo",
            "interval_semantics": "half-open",
            "recording_split": (
                "external_confirmation_all_evaluation"
                if evaluation_only
                else "deterministic_sha256_60_calibration_40_evaluation"
            ),
            "recording_split_seed": None if evaluation_only else RECORDING_SPLIT_SEED,
            "evaluation_quotas_by_sample_rate_hz": {
                str(rate): quota
                for rate, quota in sorted(({} if evaluation_only else EVALUATION_QUOTAS).items())
            },
            "membership_uses_detection_outcomes": False,
        },
        "recordings": recordings,
        "groups": groups,
        "windows": output_windows,
        "counts": {
            "recordings": len(recordings),
            "groups": len(groups),
            "windows": len(output_windows),
            "windows_by_role": {role: role_counts[role] for role in ROLES},
            "recordings_by_split": dict(sorted(split_counts.items())),
        },
        "overlap_validation": {
            "connected_groups_cross_roles": 0,
            "windows_with_both_receivers": sum(
                item["receiver_ids"] == [0, 1] for item in output_windows
            ),
            "all_overlapping_support_is_grouped": True,
        },
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}: row must be an object")
            rows.append(value)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--opportunities", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--evaluation-only",
        action="store_true",
        help="Explicit external confirmation panel; never fits shared coefficients",
    )
    args = parser.parse_args()
    document = build_partition(read_jsonl(args.opportunities), evaluation_only=args.evaluation_only)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
