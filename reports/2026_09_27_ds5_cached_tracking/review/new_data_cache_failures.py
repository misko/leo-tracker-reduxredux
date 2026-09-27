#!/usr/bin/env python3
"""Receipt-only classification of failed predictions in the new-data V6 replay."""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def circular(delta: float, rate: int) -> float:
    period = rate / 750
    return (delta + period / 2) % period - period / 2


def anchor(row: dict, value: dict) -> tuple[int, float, float]:
    whole = math.floor(value["epoch_samples"])
    integer = row["start_counter"] + value["window"] * (row["rate_hz"] // 50) + whole
    return integer, value["epoch_samples"] - whole, value["cfo_hz"]


def difference(left: tuple[int, float, float], right: tuple[int, float, float], rate: int) -> dict:
    samples = (left[0] - right[0]) + (left[1] - right[1])
    return {"timing_error_samples": abs(circular(samples, rate)),
            "timing_error_us": abs(circular(samples, rate)) / rate * 1e6,
            "cfo_error_hz": abs(left[2] - right[2])}


def associated(error: dict) -> bool:
    return error["timing_error_us"] <= 2 and error["cfo_error_hz"] <= 8000


def learning_compatible(past: tuple[int, float, float], current: tuple[int, float, float], rate: int) -> bool:
    elapsed = (current[0] - past[0]) + (current[1] - past[1])
    dt = elapsed / rate
    return (0 < dt <= 2.12
            and abs(circular(elapsed, rate)) <= 50e-6 * rate * dt + rate * 2e-6
            and abs(current[2] - past[2]) <= 5000 * dt + 2000)


def run() -> dict:
    receipt_path = ROOT / "new_data_v6.json"
    source_path = ROOT / "tracking.py"
    receipt = json.loads(receipt_path.read_text())
    if sha256(source_path) != receipt["source_sha256"]["tracking.py"]:
        raise ValueError("tracker differs from replay receipt")
    failures = [row for row in receipt["rows"] if row["reason"] == "failed_prediction"]
    if len(failures) != 52 or sum(row["reference_positive"] for row in failures) != 38:
        raise ValueError("unexpected failed-prediction population")

    history: dict[tuple, list[dict]] = {}
    rows = []
    for row in sorted(receipt["rows"], key=lambda item: (item["start_counter"], item["rx"])):
        key = (row["session_id"], row["rx"], row["channel"], row["edge"], row["rate_hz"])
        reference = anchor(row, row["reference"])
        if row["reason"] == "failed_prediction":
            prediction = anchor(row, row["prediction"])
            error = difference(prediction, reference, row["rate_hz"])
            local = error["timing_error_samples"] <= .5 and error["cfo_error_hz"] <= 8000
            probed = error["timing_error_samples"] <= 1 and error["cfo_error_hz"] <= 8000
            if local:
                category = "inside_bracketed_local_correction_envelope"
            elif associated(error):
                category = "associated_but_outside_half_sample_correction"
            elif error["cfo_error_hz"] <= 8000:
                category = "cfo_compatible_timing_other"
            elif error["timing_error_us"] <= 2:
                category = "timing_compatible_cfo_other"
            else:
                category = "timing_and_cfo_other"
            direct, reachable = [], []
            for old in history.get(key, []):
                old_error = difference(old["anchor"], reference, row["rate_hz"])
                age = (row["start_counter"] - old["start_counter"]) / row["rate_hz"]
                if 0 < age <= 2 and associated(old_error):
                    direct.append(old["visit_index"])
                if learning_compatible(old["anchor"], reference, row["rate_hz"]):
                    reachable.append(old["visit_index"])
            rows.append({
                "case_id": row["case_id"], "visit_index": row["visit_index"], "receiver": row["rx"],
                "channel": row["channel"], "rate_hz": row["rate_hz"], "edge": row["edge"],
                "reference_positive": row["reference_positive"], **error,
                "prediction_associated": associated(error), "category": category,
                "inside_bracketed_local_correction_envelope": local,
                "inside_three_cell_probed_span": probed,
                "prior_reference_direct_matches_within_2s": direct,
                "prior_reference_learning_compatible": reachable,
            })
        if row["reference_positive"]:
            history.setdefault(key, []).append({"visit_index": row["visit_index"],
                                                "start_counter": row["start_counter"],
                                                "anchor": reference})

    def summary(items: list[dict]) -> dict:
        counter = Counter(item["category"] for item in items)
        switched = [item for item in items if not item["prediction_associated"]]
        return {"receiver_visits": len(items), "categories": dict(sorted(counter.items())),
                "prediction_associated": sum(item["prediction_associated"] for item in items),
                "inside_bracketed_local_correction_envelope": sum(
                    item["inside_bracketed_local_correction_envelope"] for item in items),
                "inside_three_cell_probed_span": sum(item["inside_three_cell_probed_span"] for item in items),
                "outside_prediction_association": len(switched),
                "outside_association_with_direct_prior_match": sum(
                    bool(item["prior_reference_direct_matches_within_2s"]) for item in switched),
                "outside_association_with_oracle_reachable_prior": sum(
                    bool(item["prior_reference_learning_compatible"]) for item in switched)}

    positives = [row for row in rows if row["reference_positive"]]
    payload = {
        "schema": "org.leo.research.new-data-cache-failure-diagnostic/v1",
        "scope": "receipt-only post-outcome development diagnostic",
        "qualification_result": False,
        "iq_opened": False,
        "runtime_policy_changed": False,
        "receipt_sha256": sha256(receipt_path),
        "tracking_sha256": sha256(source_path),
        "runner_sha256": sha256(Path(__file__).resolve()),
        "local_recovery_contract": {
            "grid_offsets_samples": [-1, 0, 1],
            "accepted_peak_must_be_center": True,
            "parabolic_correction_samples": [-0.5, 0.5],
            "metadata_envelope_is_necessary_not_sufficient": True,
        },
        "oracle_history_contract": {
            "uses_only_earlier_same_key_reference_positive_observations": True,
            "direct_match_age_seconds": 2,
            "reachable_bound_age_seconds": 2.12,
            "maximum_clock_error_ppm": 50,
            "maximum_cfo_rate_hz_per_s": 5000,
            "learning_cfo_slack_hz": 2000,
            "warning": "Reference identity selects the compatible history after outcomes; counts are upper bounds, not a causal strategy.",
        },
        "summary": {"all_failures": summary(rows), "reference_positive_failures": summary(positives)},
        "rows": rows,
    }
    output = ROOT / "new_data_cache_failures.json"
    if output.exists():
        raise FileExistsError(output)
    output.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    return payload


if __name__ == "__main__":
    run()
