#!/usr/bin/env python3
"""Recompute full-72 fitted-tau versus host-bracket summaries read-only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def quantiles(values, probabilities):
    return [float(value) for value in np.quantile(values, probabilities)]


def compute(qualification_path: Path, inference_path: Path) -> dict:
    qualification = json.loads(qualification_path.read_text())
    inference = json.loads(inference_path.read_text())
    group = next(item for item in qualification["groups"] if item["loaded_scan_count"] == 72)
    scans = {item["session_id"]: item for item in group["scans"]}
    session_ids = inference["session_ids"]
    if len(session_ids) != 72 or set(session_ids) != set(scans):
        raise ValueError("sealed inference and 00Z qualification sessions differ")
    widths_ns = np.asarray([scans[item]["first_sample_bracket_width_ns"] for item in session_ids])
    arms = []
    for arm in inference["arms"]:
        tau = np.asarray([arm["taus_s"][item] for item in session_ids])
        ratio = np.abs(tau) / (widths_ns / 1e9)
        arms.append(
            {
                "prior": arm["prior"],
                "scale_s": arm["scale_s"],
                "active_tau_count": arm["active_tau_count"],
                "tau_s_quantiles_0_10_50_90_100": quantiles(tau, [0, 0.1, 0.5, 0.9, 1]),
                "abs_tau_s_quantiles_10_50_90_100": quantiles(abs(tau), [0.1, 0.5, 0.9, 1]),
                "abs_tau_to_bracket_width_ratio_quantiles_50_90_100": quantiles(
                    ratio, [0.5, 0.9, 1]
                ),
                "first_scan_id": session_ids[0],
                "first_scan_tau_s": float(tau[0]),
                "first_scan_abs_tau_over_width": float(ratio[0]),
                "per_scan_abs_tau_over_bracket_width": {
                    session: float(value) for session, value in zip(session_ids, ratio, strict=True)
                },
            }
        )
    return {
        "schema": "full8h-tau-timing-numerical-audit/v1",
        "membership": {
            "qualification_scan_count": len(scans),
            "inference_scan_count": len(session_ids),
            "same_session_id_set": True,
        },
        "timing_metadata": {
            "algorithm": "host-bracketed-device-counter-utc-v1",
            "stream_generation": sorted({item["stream_generation"] for item in scans.values()}),
            "first_sample_bracket_width_ns_quantiles_0_10_50_90_100": [
                int(np.quantile(widths_ns, probability)) for probability in [0, 0.1, 0.5, 0.9, 1]
            ],
            "first_scan_id": session_ids[0],
            "first_scan_bracket_width_ns": int(widths_ns[0]),
            "all_timing_qualified": all(item["timing_qualified"] for item in scans.values()),
        },
        "tau_summaries": arms,
        "bindings": {
            "qualification_results": digest(qualification_path),
            "shared_epoch_inference": digest(inference_path),
            "helper": digest(Path(__file__)),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qualification", type=Path, required=True)
    parser.add_argument("--inference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-results", type=Path)
    args = parser.parse_args()
    result = compute(args.qualification, args.inference)
    if args.verify_results:
        recorded = json.loads(args.verify_results.read_text())
        for key in ("membership", "timing_metadata", "tau_summaries"):
            expected = recorded[key]
            if key == "tau_summaries":
                expected = [
                    {
                        name: value
                        for name, value in arm.items()
                        if name != "per_scan_abs_tau_over_bracket_width"
                    }
                    for arm in expected
                ]
                actual = [
                    {
                        name: value
                        for name, value in arm.items()
                        if name != "per_scan_abs_tau_over_bracket_width"
                    }
                    for arm in result[key]
                ]
            else:
                actual = result[key]
            if actual != expected:
                raise ValueError(f"recorded {key} differs from recomputation")
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
