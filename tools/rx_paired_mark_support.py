"""Export frequency-free paired receiver candidate-count and margin support."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

RECEIVERS = ("rx0", "rx1")
ROLES = ("reception", "held_frequency")


def _margin_receipt(candidates):
    finite = []
    missing = 0
    nonfinite = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("receiver candidates must be objects")
        if "fractional_margin" not in candidate or candidate["fractional_margin"] is None:
            missing += 1
            continue
        try:
            value = float(candidate["fractional_margin"])
        except (TypeError, ValueError) as exc:
            raise ValueError("candidate fractional_margin must be numeric or null") from exc
        if not math.isfinite(value):
            nonfinite += 1
        else:
            finite.append(value)
    return {
        "finite": finite,
        "finite_count": len(finite),
        "missing_count": missing,
        "nonfinite_count": nonfinite,
        "mean": math.fsum(finite) / len(finite) if finite else None,
    }


def _window(window):
    role = window.get("role")
    if role not in ROLES:
        raise ValueError("window role must be reception or held_frequency")
    observed = window.get("observed")
    if not isinstance(observed, dict) or set(observed) != set(RECEIVERS):
        raise ValueError("window observed must contain exactly rx0 and rx1")
    if any(not isinstance(observed[receiver], list) for receiver in RECEIVERS):
        raise ValueError("receiver candidate collections must be lists")
    counts = {receiver: len(observed[receiver]) for receiver in RECEIVERS}
    margins = {receiver: _margin_receipt(observed[receiver]) for receiver in RECEIVERS}
    total = counts["rx0"] + counts["rx1"]
    return {
        "source_window_id": window.get("source_window_id"),
        "prediction_utc_ns": window.get("prediction_utc_ns"),
        "role": role,
        "candidate_counts": counts,
        "count_difference_rx1_minus_rx0": counts["rx1"] - counts["rx0"],
        "count_asymmetry_rx1_minus_rx0": (
            (counts["rx1"] - counts["rx0"]) / total if total else None
        ),
        "mean_fractional_margin": {receiver: margins[receiver]["mean"] for receiver in RECEIVERS},
        "mean_margin_contrast_rx1_minus_rx0": (
            margins["rx1"]["mean"] - margins["rx0"]["mean"]
            if margins["rx0"]["mean"] is not None and margins["rx1"]["mean"] is not None
            else None
        ),
        "margin_quality": {
            receiver: {
                "finite_count": margins[receiver]["finite_count"],
                "missing_count": margins[receiver]["missing_count"],
                "nonfinite_count": margins[receiver]["nonfinite_count"],
            }
            for receiver in RECEIVERS
        },
        "_finite_margins": {receiver: margins[receiver]["finite"] for receiver in RECEIVERS},
    }


def _aggregate(rows):
    categories = Counter()
    differences = []
    margins = {receiver: [] for receiver in RECEIVERS}
    quality = {receiver: Counter() for receiver in RECEIVERS}
    for row in rows:
        n0, n1 = row["candidate_counts"]["rx0"], row["candidate_counts"]["rx1"]
        category = (
            "both_empty"
            if n0 == n1 == 0
            else "only_rx0"
            if n0 and not n1
            else "only_rx1"
            if n1 and not n0
            else "both_nonempty"
        )
        categories[category] += 1
        differences.append(row["count_difference_rx1_minus_rx0"])
        for receiver in RECEIVERS:
            margins[receiver].extend(row["_finite_margins"][receiver])
            quality[receiver].update(row["margin_quality"][receiver])
    return {
        "qualified_windows": len(rows),
        "window_support": {
            name: categories[name]
            for name in ("both_empty", "only_rx0", "only_rx1", "both_nonempty")
        },
        "count_difference_rx1_minus_rx0": {
            "values": differences,
            "mean": math.fsum(differences) / len(differences) if differences else None,
        },
        "fractional_margin": {
            receiver: {
                "finite_values": margins[receiver],
                "finite_count": len(margins[receiver]),
                "missing_count": quality[receiver]["missing_count"],
                "nonfinite_count": quality[receiver]["nonfinite_count"],
                "mean": (
                    math.fsum(margins[receiver]) / len(margins[receiver])
                    if margins[receiver]
                    else None
                ),
            }
            for receiver in RECEIVERS
        },
    }


def analyze(document):
    if document.get("schema") != "rx-geometry-dataset/v1":
        raise ValueError("unsupported geometry dataset")
    lanes = []
    sessions = set()
    seen_windows = set()
    for source in document.get("lanes", []):
        if source.get("recording_split") != "calibration":
            continue
        lane = source.get("lane", {})
        session_id = lane.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("calibration lane lacks session_id")
        sessions.add(session_id)
        rows = []
        for window in source.get("windows", []):
            row = _window(window)
            window_id = row["source_window_id"]
            if not isinstance(window_id, str) or not window_id or window_id in seen_windows:
                raise ValueError("source window IDs must be nonempty and globally unique")
            if not isinstance(row["prediction_utc_ns"], int):
                raise ValueError("prediction timestamp must be an integer")
            seen_windows.add(window_id)
            rows.append(row)
        public_rows = [
            {key: value for key, value in row.items() if key != "_finite_margins"} for row in rows
        ]
        lanes.append(
            {
                "lane": lane,
                "session_id": session_id,
                "roles": {
                    role: _aggregate([row for row in rows if row["role"] == role]) for role in ROLES
                },
                "windows": public_rows,
            }
        )
    if len(sessions) != 6:
        raise ValueError("expected exactly six calibration recordings")
    return {
        "schema": "rx-paired-mark-support/v1",
        "status": "complete",
        "calibration_sessions": sorted(sessions),
        "lanes": lanes,
        "semantics": (
            "fractional_margin is a detector score margin, not an amplitude; no frequency "
            "value or frequency gate is used."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload = args.dataset.read_bytes()
    result = analyze(json.loads(payload))
    result["dataset_sha256"] = hashlib.sha256(payload).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
