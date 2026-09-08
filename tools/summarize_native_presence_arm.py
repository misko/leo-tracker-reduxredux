#!/usr/bin/env python3
"""Verify saved ARM replay output against matching desktop variants and summarize it."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from tools.qualify_native_presence import digest, write_json


def verify_replay(text, inputs, desktop, variant, repeats, sample_format):
    expected = {p["file"]: p for p in inputs}
    references = {r["probe"]: r["result"] for r in desktop if r["variant"] == variant}
    counts, rows, name = {}, [], None
    if not expected or repeats < 2 or sample_format not in (1, 2):
        raise ValueError("nonempty repeated replay and explicit sample format required")
    for line in text.splitlines():
        if not line.startswith("{"):
            sha, path = line.split()
            name = Path(path).name
            if name not in expected or name in counts or expected[name]["sha256"] != sha:
                raise ValueError("unexpected, duplicate, or changed input probe")
            counts[name] = 0
            continue
        if name is None:
            raise ValueError("result without input identity")
        row = json.loads(line)
        probe = expected[name]
        if (
            row["schema"] != "native-presence-replay-profile-v1"
            or row["iteration"] != counts[name]
            or row["format"] != sample_format
            or row["device_counter"] != probe["device_counter"]
            or row["rate_hz"] != probe["rate_hz"]
            or row["edge"] != int(probe["edge"] == "upper")
        ):
            raise ValueError("replay identity or sequence mismatch")
        counts[name] += 1
        reference = references[name]
        if len(row["candidates"]) != len(reference["candidates"]):
            raise ValueError("candidate inventory mismatch")
        for got, want in zip(row["candidates"], reference["candidates"], strict=True):
            if got.keys() != want.keys():
                raise ValueError("candidate field mismatch")
            for key in got:
                if key in ("epoch", "fractional_complete"):
                    if got[key] != want[key]:
                        raise ValueError("candidate epoch or refinement mismatch")
                else:
                    atol = 0.001 if "cfo" in key else (1e-7 if "offset" in key else 1e-10)
                    if (
                        not math.isfinite(got[key])
                        or not math.isfinite(want[key])
                        or not math.isclose(got[key], want[key], rel_tol=1e-9, abs_tol=atol)
                    ):
                        raise ValueError(f"candidate numerical mismatch: {key}")
            if (got["margin"] >= 0.025) != (want["margin"] >= 0.025):
                raise ValueError("candidate gate mismatch")
        for key in ("total_cpu_ms", "total_wall_ms"):
            if not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("invalid execution duration")
        rows.append({"probe": name, **row})
    if counts.keys() != expected.keys() or any(n != repeats for n in counts.values()):
        raise ValueError("incomplete replay")
    return rows


def summarize(rows):
    return {
        str(rate): {
            group: {
                key: dict(
                    zip(
                        ("p50", "p95", "p99", "max"),
                        np.quantile(
                            [
                                r[key]
                                for r in rows
                                if r["rate_hz"] == rate
                                and (r["iteration"] == 0) == (group == "first_execution")
                            ],
                            [0.5, 0.95, 0.99, 1],
                        ).tolist(),
                        strict=True,
                    )
                )
                for key in ("total_cpu_ms", "total_wall_ms")
            }
            for group in ("first_execution", "warmed")
        }
        for rate in sorted({r["rate_hz"] for r in rows})
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("desktop", type=Path)
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--format", dest="sample_format", type=int, choices=(1, 2), required=True)
    parser.add_argument("--repeats", type=int, default=20)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(
        Path("/mnt/qnap01")
    ) or args.output.resolve().is_relative_to(Path("/srv/bulk/leo")):
        raise ValueError("summary cannot be written beneath archive storage")
    rows = verify_replay(
        args.raw.read_text(),
        json.loads(args.inputs.read_text()),
        json.loads(args.desktop.read_text()),
        args.variant,
        args.repeats,
        args.sample_format,
    )
    result = {
        "schema": "org.leo.research.arm-presence-runtime-summary/v1",
        "variant": args.variant,
        "probe_count": len({r["probe"] for r in rows}),
        "iterations_per_probe": args.repeats,
        "execution_count": len(rows),
        "sample_format": args.sample_format,
        "all_candidate_outputs_match_desktop": True,
        "raw_sha256": digest(args.raw),
        "inputs_sha256": digest(args.inputs),
        "desktop_sha256": digest(args.desktop),
        "verifier_sha256": digest(Path(__file__)),
        "limitations": "Repeated saved probes, not independent signal trials or streaming. "
        "Initialization and file IO excluded. CPU accounting on this ARM has coarse granularity. "
        "Binary/radio identity comes from the enclosing execution receipt, not this parser.",
        "rates": summarize(rows),
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
