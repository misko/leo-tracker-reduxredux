#!/usr/bin/env python3
"""Package and verify bounded repeated-probe worker loads, never RF collection."""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path

import numpy as np

from tools.qualify_native_presence import digest, write_json
from tools.summarize_presence_holdout import validate_one


def prepare(source: Path, output: Path, rate: int):
    """Use all first-window probes at one rate; do not select on detector output."""
    if rate not in (2500000, 5000000):
        raise ValueError("unqualified rate")
    if any(output.resolve().is_relative_to(Path(p)) for p in ("/srv/bulk/leo", "/mnt/qnap01")):
        raise ValueError("output cannot be beneath archive storage")
    inputs = json.loads((source / "inputs.json").read_text())
    source_rows = json.loads((source / "results.json").read_text())
    references = {r["probe"]: r for r in source_rows}
    if len(references) != len(source_rows):
        raise ValueError("duplicate reference rows")
    selected = [
        p for p in inputs if p["rate_hz"] == rate and p["provenance"]["probe_offset_ms"] == 0
    ]
    if not 1 <= len(selected) <= 96 or len({p["file"] for p in selected}) != len(selected):
        raise ValueError("bounded unique first-window inventory required")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    with (output / "probes.pack").open("xb") as pack:
        pack.write(struct.pack("<4sII", b"LPP1", rate, len(selected)))
        for p in selected:
            validate_one(
                p,
                references[p["file"]],
                {
                    "maximum_cfo_difference_hz": 8000,
                    "maximum_circular_epoch_difference_us": 2,
                },
            )
            if Path(p["file"]).name != p["file"]:
                raise ValueError("probe path must be a basename")
            path = source / p["file"]
            if digest(path) != p["sha256"]:
                raise ValueError("probe hash mismatch")
            data = path.read_bytes()
            magic, actual_rate, edge, count, fmt, counter = struct.unpack("<4sIIIIQ", data[:28])
            offset = 28 + round(rate / 750) * 32
            if (
                magic != b"LPR1"
                or actual_rate != rate
                or edge != int(p["edge"] == "upper")
                or count != rate // 50
                or fmt != 2
                or str(counter) != p["device_counter"]
                or len(data) != offset + count * 4
                or p["provenance"]["rx"] != 1
            ):
                raise ValueError("probe geometry mismatch")
            pack.write(
                struct.pack(
                    "<QQII", counter, p["provenance"]["visit"], edge, p["provenance"]["channel"]
                )
            )
            pack.write(data[offset:])
            records.append({**p, "expected": references[p["file"]]["result"]})
    write_json(
        output / "manifest.json",
        {
            "schema": "org.leo.research.presence-worker-pack/v1",
            "rate_hz": rate,
            "pack_sha256": digest(output / "probes.pack"),
            "records": records,
            "source_inputs_sha256": digest(source / "inputs.json"),
            "source_results_sha256": digest(source / "results.json"),
            "scope": "Repeated first-window saved probes at 126 ms; not an original scan timeline.",
        },
    )


def compare_values(got, expected, *, nuisance=False):
    fields = set(expected) - ({"cpu_ms"} if nuisance else set())
    if set(got) != fields:
        raise ValueError("candidate or nuisance fields differ")
    for key in fields:
        a, b = got[key], expected[key]
        if key in ("enabled", "applied", "epoch", "fractional_complete"):
            if a != b:
                raise ValueError("candidate or nuisance decision differs")
        else:
            atol = (
                0.001
                if "cfo" in key or key == "frequency_hz"
                else (1e-7 if "offset" in key else 1e-10)
            )
            if (
                not math.isfinite(a)
                or not math.isfinite(b)
                or not math.isclose(a, b, rel_tol=1e-9, abs_tol=atol)
            ):
                raise ValueError(f"candidate or nuisance numerical mismatch: {key}")
    if not nuisance and (got["margin"] >= 0.025) != (expected["margin"] >= 0.025):
        raise ValueError("candidate gate differs")


def verify(text: str, manifest: dict, duration: int):
    if (
        manifest["schema"] != "org.leo.research.presence-worker-pack/v1"
        or not 126 <= duration <= 300000
    ):
        raise ValueError("unqualified manifest or duration")
    lines = [json.loads(line) for line in text.splitlines()]
    if not lines or lines[-1]["schema"] != "native-worker-paced-summary-v1":
        raise ValueError("terminal worker summary missing")
    terminal, rows = lines[-1], lines[:-1]
    jobs, rate = (duration + 125) // 126, manifest["rate_hz"]
    if (
        terminal["rate_hz"] != rate
        or terminal["duration_ms"] != duration
        or terminal["submitted"] != jobs
        or terminal["completed"] != jobs
        or terminal["dropped"] != 0
        or terminal["skipped"] != 0
        or len(rows) != jobs
        or not duration <= terminal["elapsed_ms"] <= duration + 5000
    ):
        raise ValueError("incomplete, dropped, or incorrectly paced workload")
    records = manifest["records"]
    for seq, row in enumerate(rows):
        p = records[seq % len(records)]
        if (
            row["schema"] != "native-worker-paced-result-v1"
            or row["sequence"] != seq
            or row["probe_index"] != seq % len(records)
            or row["rate_hz"] != rate
            or row["device_counter"] != p["device_counter"]
            or row["status"] != 0
            or row["edge"] != int(p["edge"] == "upper")
            or row["channel"] != p["provenance"]["channel"]
            or row["visit"] != p["provenance"]["visit"]
        ):
            raise ValueError("worker result identity mismatch")
        expected = p["expected"]
        if len(row["candidates"]) != len(expected["candidates"]):
            raise ValueError("candidate count mismatch")
        for a, b in zip(row["candidates"], expected["candidates"], strict=True):
            compare_values(a, b)
        compare_values(row["nuisance"], expected["nuisance"], nuisance=True)
        for key in ("total_cpu_ms", "total_wall_ms", "delivery_latency_ms"):
            if not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("invalid duration")

    def distribution(values):
        return dict(
            zip(
                ("p50", "p95", "p99", "max"),
                np.quantile(values, [0.5, 0.95, 0.99, 1]).tolist(),
                strict=True,
            )
        )

    return {
        "schema": "org.leo.research.presence-worker-paced-verification/v1",
        "all_outputs_match_desktop": True,
        "terminal": terminal,
        "unique_probes": len({r["probe_index"] for r in rows}),
        "pack_probe_count": len(records),
        "executions": len(rows),
        "timings": {
            key: distribution([r[key] for r in rows])
            for key in ("total_cpu_ms", "total_wall_ms", "delivery_latency_ms")
        },
        "first_lower_and_upper": [
            next(r for r in rows if r["edge"] == edge) for edge in sorted({r["edge"] for r in rows})
        ],
        "limitations": "Repeated saved probes, not independent signal trials or original DMA "
        "arrivals. No RF, receive interrupts, dual-RX forwarding, late hop metadata, or network "
        "acquisition contention. Worker initialization and input loading excluded from timings.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    package = sub.add_parser("prepare")
    package.add_argument("source", type=Path)
    package.add_argument("output", type=Path)
    package.add_argument("rate", type=int)
    check = sub.add_parser("verify")
    check.add_argument("manifest", type=Path)
    check.add_argument("raw", type=Path)
    check.add_argument("output", type=Path)
    check.add_argument("duration", type=int)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.source, args.output, args.rate)
    else:
        if any(
            args.output.resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")
        ):
            raise ValueError("output cannot be beneath archive storage")
        result = verify(args.raw.read_text(), json.loads(args.manifest.read_text()), args.duration)
        result.update(
            raw_sha256=digest(args.raw),
            manifest_sha256=digest(args.manifest),
            verifier_sha256=digest(Path(__file__)),
        )
        write_json(args.output, result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
