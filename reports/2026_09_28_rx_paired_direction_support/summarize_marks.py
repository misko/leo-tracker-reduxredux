"""Independently audit and summarize frozen paired receiver mark support."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROLES = ("reception", "held_frequency")
CATEGORIES = ("both_empty", "only_rx0", "only_rx1", "both_nonempty")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(left, right) -> None:
    if left is None or right is None:
        assert left is right
    else:
        assert math.isclose(float(left), float(right), rel_tol=0, abs_tol=1e-15)


def classify(n0: int, n1: int) -> str:
    if n0 == n1 == 0:
        return "both_empty"
    if n0 and not n1:
        return "only_rx0"
    if n1 and not n0:
        return "only_rx1"
    return "both_nonempty"


def summarize(rows: list[dict]) -> dict:
    counts = Counter(row["category"] for row in rows)
    total = len(rows)
    return {
        "windows": total,
        "counts": {name: counts[name] for name in CATEGORIES},
        "rates": {name: counts[name] / total if total else None for name in CATEGORIES},
        "mean_count_difference_rx1_minus_rx0": (
            math.fsum(row["difference"] for row in rows) / total if total else None
        ),
        "mean_count_asymmetry_rx1_minus_rx0": (
            math.fsum(row["asymmetry"] for row in rows if row["asymmetry"] is not None)
            / sum(row["asymmetry"] is not None for row in rows)
            if any(row["asymmetry"] is not None for row in rows)
            else None
        ),
    }


def run(dataset: dict, marks: dict) -> dict:
    if dataset.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported source dataset")
    if marks.get("schema") != "rx-paired-mark-support/v1":
        raise ValueError("unsupported paired mark export")
    exported = {row["source_window_id"]: row for lane in marks["lanes"] for row in lane["windows"]}
    if len(exported) != sum(len(lane["windows"]) for lane in marks["lanes"]):
        raise ValueError("paired mark export repeats a source window")
    rows = []
    margins = {"rx0": [], "rx1": []}
    missing = nonfinite = 0
    for lane in dataset["lanes"]:
        if lane.get("recording_split") != "calibration":
            continue
        session_id = lane["lane"]["session_id"]
        for window in lane["windows"]:
            observed = window["observed"]
            n0, n1 = len(observed["rx0"]), len(observed["rx1"])
            total = n0 + n1
            receiver_means = {}
            quality = {}
            for receiver in ("rx0", "rx1"):
                values = []
                receiver_missing = receiver_nonfinite = 0
                for candidate in observed[receiver]:
                    value = candidate.get("fractional_margin")
                    if value is None:
                        receiver_missing += 1
                    elif not math.isfinite(float(value)):
                        receiver_nonfinite += 1
                    else:
                        values.append(float(value))
                        margins[receiver].append(float(value))
                missing += receiver_missing
                nonfinite += receiver_nonfinite
                receiver_means[receiver] = math.fsum(values) / len(values) if values else None
                quality[receiver] = (len(values), receiver_missing, receiver_nonfinite)
            expected = exported.pop(window["source_window_id"])
            assert expected["prediction_utc_ns"] == window["prediction_utc_ns"]
            assert expected["role"] == window["role"]
            assert expected["candidate_counts"] == {"rx0": n0, "rx1": n1}
            assert expected["count_difference_rx1_minus_rx0"] == n1 - n0
            close(expected["count_asymmetry_rx1_minus_rx0"], (n1 - n0) / total if total else None)
            for receiver in ("rx0", "rx1"):
                close(expected["mean_fractional_margin"][receiver], receiver_means[receiver])
                receipt = expected["margin_quality"][receiver]
                assert (
                    receipt["finite_count"],
                    receipt["missing_count"],
                    receipt["nonfinite_count"],
                ) == quality[receiver]
            contrast = (
                receiver_means["rx1"] - receiver_means["rx0"]
                if receiver_means["rx0"] is not None and receiver_means["rx1"] is not None
                else None
            )
            close(expected["mean_margin_contrast_rx1_minus_rx0"], contrast)
            rows.append(
                {
                    "session_id": session_id,
                    "role": window["role"],
                    "category": classify(n0, n1),
                    "difference": n1 - n0,
                    "asymmetry": (n1 - n0) / total if total else None,
                }
            )
    if exported:
        raise ValueError("paired mark export contains windows outside calibration source")
    if missing or nonfinite:
        raise ValueError("frozen source unexpectedly contains missing/nonfinite margins")
    sessions = sorted({row["session_id"] for row in rows})
    if sessions != marks["calibration_sessions"] or len(sessions) != 6:
        raise ValueError("calibration session membership mismatch")
    pooled = {role: summarize([row for row in rows if row["role"] == role]) for role in ROLES}
    per_record = {
        session: {
            role: summarize(
                [row for row in rows if row["session_id"] == session and row["role"] == role]
            )
            for role in ROLES
        }
        for session in sessions
    }
    equal_record = {}
    for role in ROLES:
        equal_record[role] = {
            "records": len(sessions),
            "rates": {
                category: math.fsum(per_record[s][role]["rates"][category] for s in sessions)
                / len(sessions)
                for category in CATEGORIES
            },
        }
    duplicate_receipt = {}
    for receiver, values in margins.items():
        counts = Counter(values)
        duplicate_receipt[receiver] = {
            "finite_candidates": len(values),
            "distinct_margin_values": len(counts),
            "values_repeated": sum(count > 1 for count in counts.values()),
            "duplicate_occurrences_beyond_first": sum(count - 1 for count in counts.values()),
            "note": "Exact margin-value repetition is descriptive; no candidate is deduplicated.",
        }
    return {
        "schema": "rx-paired-mark-summary/v1",
        "status": "passed",
        "calibration_sessions": sessions,
        "verified_windows": len(rows),
        "margin_quality": {"missing": missing, "nonfinite": nonfinite},
        "pooled_by_role": pooled,
        "per_record_by_role": per_record,
        "equal_record_by_role": equal_record,
        "duplicate_margin_receipt": duplicate_receipt,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--marks", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(json.loads(args.dataset.read_text()), json.loads(args.marks.read_text()))
    result["source_sha256"] = {
        "dataset": digest(args.dataset),
        "paired_mark": digest(args.marks),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
