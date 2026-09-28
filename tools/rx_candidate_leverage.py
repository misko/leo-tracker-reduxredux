"""Describe frozen candidate probability concentration without consuming detections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


def summarize(bank: dict, partitions: dict) -> dict:
    splits = {row["session_id"]: row["recording_split"] for row in partitions["recordings"]}
    tracks = []
    for track in bank["tracks"]:
        candidates = track["top_candidates"]
        weights = [float(row["conditional_top3_probability"]) for row in candidates]
        if not weights or any(not math.isfinite(p) or p < 0 for p in weights):
            raise ValueError("invalid candidate weights")
        if abs(sum(weights) - 1) > 1e-8:
            raise ValueError("conditional weights do not sum to one")
        mass = float(track["retained_catalogue_probability_mass"])
        entropy = -sum(p * math.log(p) for p in weights if p > 0)
        tracks.append(
            {
                "session_id": track["session_id"],
                "track_id": track["track_id"],
                "recording_split": splits[track["session_id"]],
                "maximum_conditional_weight": max(weights),
                "conditional_entropy_nats": entropy,
                "effective_candidate_count": math.exp(entropy),
                "conditional_top_weight_headroom": max(0.0, 1 - max(weights)),
                "retained_catalogue_mass": mass,
                "omitted_catalogue_mass": max(0.0, 1 - mass),
                "positive_weight_candidates": sum(p > 0 for p in weights),
                "candidates": [
                    {"catalog_number": c["catalog_number"], "weight": p}
                    for c, p in zip(candidates, weights, strict=True)
                ],
            }
        )
    groups = {}
    for split in ["all", *sorted(set(splits.values()))]:
        selected = [t for t in tracks if split == "all" or t["recording_split"] == split]
        groups[split] = {
            "tracks": len(selected),
            "top_weight_ge_0p99": sum(t["maximum_conditional_weight"] >= 0.99 for t in selected),
            "top_weight_ge_0p999999": sum(
                t["maximum_conditional_weight"] >= 0.999999 for t in selected
            ),
            "exact_unit_top_weight": sum(t["maximum_conditional_weight"] == 1 for t in selected),
            "mean_entropy_nats": sum(t["conditional_entropy_nats"] for t in selected)
            / len(selected),
            "maximum_omitted_catalogue_mass": max(t["omitted_catalogue_mass"] for t in selected),
            "positive_weight_candidate_counts": dict(
                Counter(t["positive_weight_candidates"] for t in selected)
            ),
        }
    return {
        "schema": "rx-candidate-leverage/v1",
        "groups": groups,
        "tracks": tracks,
        "interpretation": "Conditional model probabilities, "
        "not calibrated identification confidence. "
        "Exact zero weights cannot be revived by multiplicative likelihood reweighting.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-bank", type=Path, required=True)
    parser.add_argument("--partitions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payloads = {
        name: path.read_bytes()
        for name, path in [("candidate_bank", args.candidate_bank), ("partitions", args.partitions)]
    }
    hashes = {
        name: "sha256:" + hashlib.sha256(value).hexdigest() for name, value in payloads.items()
    }
    bank, partitions = (json.loads(payloads[name]) for name in ("candidate_bank", "partitions"))
    if bank["source_digests"]["partitions"] != hashes["partitions"]:
        raise ValueError("partition binding mismatch")
    result = summarize(bank, partitions)
    result["source_digests"] = hashes
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
