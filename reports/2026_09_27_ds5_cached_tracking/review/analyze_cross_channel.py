"""Audit raw cross-channel hypothesis reuse on an existing development replay."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def circular_error_samples(delta: float, rate_hz: int) -> float:
    period = rate_hz / 750.0
    return abs((delta + period / 2.0) % period - period / 2.0)


def audit(rows: list[dict], max_age_seconds: float = 2.0) -> dict:
    bank: dict[tuple, list[dict]] = {}
    counts = Counter()
    prior_bank_sizes = Counter()
    timing_candidate_counts = Counter()
    joint_candidate_counts = Counter()
    ordered = sorted(rows, key=lambda r: (r["session_id"], r["visit_index"], r["rx"]))
    for row in ordered:
        key = (row["session_id"], row["rx"], row["rate_hz"], row["edge"])
        prior = [entry for entry in bank.get(key, [])
                 if ((row["start_counter"] - entry["start_counter"])
                     / row["rate_hz"] <= max_age_seconds)]
        bank[key] = prior
        if not row["reference_positive"]:
            continue
        reference = row["reference"]
        counts["reference_positives"] += 1
        counts["with_any_prior_positive"] += bool(prior)
        counts["with_any_cross_channel_prior"] += any(
            entry["channel"] != row["channel"] for entry in prior)
        anchor = (row["start_counter"]
                  + reference["window"] * (row["rate_hz"] // 50)
                  + reference["epoch_samples"])
        timing = [entry for entry in prior
                  if circular_error_samples(anchor - entry["anchor"], row["rate_hz"])
                  / row["rate_hz"] <= 2e-6]
        joint = [entry for entry in timing
                 if abs(reference["cfo_hz"] - entry["cfo_hz"]) <= 8000.0]
        counts["with_timing_compatible_prior"] += bool(timing)
        counts["with_cross_channel_timing_prior"] += any(
            entry["channel"] != row["channel"] for entry in timing)
        counts["with_timing_and_cfo_prior"] += bool(joint)
        counts["with_cross_channel_timing_and_cfo_prior"] += any(
            entry["channel"] != row["channel"] for entry in joint)
        prior_bank_sizes[len(prior)] += 1
        timing_candidate_counts[len(timing)] += 1
        joint_candidate_counts[len(joint)] += 1
        bank[key].append({"start_counter": row["start_counter"], "anchor": anchor,
                          "cfo_hz": reference["cfo_hz"], "channel": row["channel"]})
    return {
        "counts": dict(counts),
        "prior_bank_size_histogram_on_positive_visits": dict(sorted(prior_bank_sizes.items())),
        "timing_candidate_count_histogram": dict(sorted(timing_candidate_counts.items())),
        "timing_and_cfo_candidate_count_histogram": dict(sorted(joint_candidate_counts.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text())
    if payload.get("split") != "dev":
        raise ValueError("this audit is development-only")
    result = {
        "schema": "org.leo.research.ds5-cross-channel-raw-bound.v1",
        "scope": "causal raw-prior audit; no drift or channel-CFO transform",
        "interpretation": (
            "Reference outcomes provide an optimistic diagnostic oracle only; "
            "they never seed the strategy and this is not a detector result."
        ),
        "input": str(args.input),
        "input_sha256": sha256(args.input),
        "script_sha256": sha256(Path(__file__)),
        "maximum_age_seconds": 2.0,
        "timing_threshold_seconds": 2e-6,
        "cfo_threshold_hz": 8000.0,
        **audit(payload["rows"]),
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
