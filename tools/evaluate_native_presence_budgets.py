#!/usr/bin/env python3
"""Bounded saved-probe experiments; never opens a radio or changes capture policy."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from tools.native_presence import ROOT, build_executable
from tools.qualify_native_presence import digest, write_json


def associated(actual, expected, rate, policy):
    period = rate / 750
    epoch_delta = (
        actual["epoch"]
        + actual["fractional_offset_samples"]
        - expected["epoch_sample"]
        - expected["fractional_offset_samples"]
    ) % period
    return (
        abs(actual["tracking_cfo_hz"] - expected["tracking_cfo_hz"])
        <= policy["maximum_cfo_difference_hz"]
        and min(epoch_delta, period - epoch_delta) / rate * 1e6
        <= policy["maximum_circular_epoch_difference_us"]
    )


def evaluate(inputs_directory: Path, output: Path, protocol_path: Path | None = None):
    output = output.resolve()
    if output.is_relative_to(Path("/mnt/qnap01")) or output.is_relative_to(Path("/srv/bulk/leo")):
        raise ValueError("results cannot be written beneath capture archives")
    output.mkdir(parents=True, exist_ok=False)
    protocol_path = protocol_path or ROOT / "config/analysis/arm-presence-budget-experiment-v1.json"
    protocol = json.loads(protocol_path.read_text())
    probes = json.loads((inputs_directory / "inputs.json").read_text())
    write_json(
        output / "protocol.json",
        {
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "inputs_sha256": digest(inputs_directory / "inputs.json"),
        },
    )
    all_results = []
    details = protocol.get("replay_details", "profile")
    if details not in ("profile", "nuisance"):
        raise ValueError("unknown replay details")
    schema = (
        "native-presence-nuisance-replay-v1"
        if details == "nuisance"
        else "native-presence-replay-profile-v1"
    )
    for variant in protocol["variants"]:
        flags = tuple(protocol["common_flags"]) + tuple(
            f"-DLEO_PRESENCE_{name}={value}" for name, value in variant["defines"].items()
        )
        binary = build_executable(output / variant["name"], cflags=flags)
        for probe in probes:
            path = inputs_directory / probe["file"]
            if path.name != probe["file"] or digest(path) != probe["sha256"]:
                raise ValueError("probe path/digest mismatch")
            process = subprocess.run(
                [str(binary), str(path), "1", "--" + details],
                capture_output=True,
                text=True,
                check=True,
                timeout=95,
            )
            row = json.loads(process.stdout)
            if (
                row["schema"] != schema
                or row["device_counter"] != probe["device_counter"]
                or row["rate_hz"] != probe["rate_hz"]
                or row["edge"] != int(probe["edge"] == "upper")
            ):
                raise ValueError("result identity mismatch")
            reference = [c for c in probe["oracle_candidates"] if c["margin"] >= 0.025]
            detected = [
                c for c in row["candidates"] if c["fractional_complete"] and c["margin"] >= 0.025
            ]
            matched = any(
                associated(a, e, probe["rate_hz"], protocol["reference_association"])
                for a in detected
                for e in reference
            )
            all_results.append(
                {
                    "variant": variant["name"],
                    "probe": probe["file"],
                    "binary_sha256": digest(binary),
                    "provenance": probe["provenance"],
                    "reference_positive": bool(reference),
                    "detected": bool(detected),
                    "matched_reference": matched,
                    "result": row,
                }
            )
        for rate in (2_500_000, 5_000_000):
            rows = [
                r
                for r in all_results
                if r["variant"] == variant["name"]
                and r["result"]["rate_hz"] == rate
                and "session_id" in r["provenance"]
            ]
            print(
                variant["name"],
                rate,
                "matched/reference",
                sum(r["matched_reference"] for r in rows),
                sum(r["reference_positive"] for r in rows),
                "any flags",
                sum(r["detected"] for r in rows),
                flush=True,
            )
    write_json(output / "results.json", all_results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--protocol", type=Path)
    args = parser.parse_args()
    evaluate(args.inputs.resolve(), args.output, args.protocol)


if __name__ == "__main__":
    main()
