#!/usr/bin/env python3
"""Prepare and verify bounded full-dwell worker replay, without opening RF."""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from tools.evaluate_presence_window_rank import load_dwells
from tools.native_presence import write_templates
from tools.presence_dwell import NativeDwell, unpack
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_worker import compare_values

FIELDS = (
    "epoch",
    "fractional_complete",
    "fractional_offset_samples",
    "acquired_cfo_hz",
    "tracking_cfo_hz",
    "exact_score",
    "control_score",
    "margin",
)
SCOPE = (
    "Repeated complete RX1 dwells with 32768-sample chunks burst-delivered every 126 ms; "
    "not original DMA/metadata timing, live acquisition, or classifier qualification."
)


def safe_output(path):
    if any(path.resolve().is_relative_to(Path(p)) for p in ("/mnt/qnap01", "/srv/bulk/leo")):
        raise ValueError("output cannot be beneath archive storage")


def prepare(source: Path, output: Path, rate: int, library: Path, *, maximum: int = 48):
    safe_output(output)
    if rate not in (2500000, 5000000) or type(maximum) is not int or not 1 <= maximum <= 48:
        raise ValueError("unqualified rate")
    receipt_path = library.with_name(library.name + ".build.json")
    receipt = json.loads(receipt_path.read_text())
    if receipt["binary_sha256"] != digest(library):
        raise ValueError("reference library hash mismatch")
    selected = [(m, iq) for m, iq in load_dwells(source) if m["rate_hz"] == rate]
    if not 1 <= len(selected) <= 48:
        raise ValueError("bounded full-dwell inventory required")
    available = len(selected)
    selected = selected[:maximum]
    references = {
        r["probe"]: r["result"] for r in json.loads((source / "results.json").read_text())
    }
    output.mkdir(parents=True, exist_ok=False)
    records = []
    write_templates(output / "templates", rate)
    with ExitStack() as stack, (output / "dwells.pack").open("xb") as pack:
        engines = {
            edge: stack.enter_context(NativeDwell(library, rate, edge, 512))
            for edge in ("lower", "upper")
        }
        pack.write(struct.pack("<4sII", b"LDP1", rate, len(selected)))
        for metadata, iq in selected:
            native = engines[metadata["edge"]]
            result = native.run(iq, maximum=1, seeded=False)
            confirmation = unpack(result.confirmations[0])
            candidates = [
                {k: c[k] for k in FIELDS}
                for c in confirmation["candidates"][: confirmation["candidate_count"]]
            ]
            original = references[metadata["source_files"][result.rank.order[0]]]["candidates"]
            if len(candidates) != len(original):
                raise ValueError("confirmation differs from original frozen candidate inventory")
            for a, b in zip(candidates, original, strict=True):
                compare_values(a, b)
            pack.write(
                struct.pack(
                    "<QQII",
                    int(metadata["counter"]),
                    metadata["visit"],
                    int(metadata["edge"] == "upper"),
                    metadata["channel"],
                )
            )
            pack.write(iq.astype("<i2", copy=False).tobytes())
            records.append(
                {
                    **metadata,
                    "expected": {
                        "candidates": candidates,
                        "nuisance": {
                            k: v for k, v in unpack(result.nuisances[0]).items() if k != "cpu_ms"
                        },
                        "rank": {
                            k: v for k, v in unpack(result.rank).items() if not k.endswith("_ms")
                        },
                        "screen_diagnostics": unpack(native.screens()),
                        "confirmation_window_mask": result.confirmation_window_mask,
                    },
                }
            )
    manifest = {
        "schema": "org.leo.research.presence-dwell-worker-pack/v1",
        "rate_hz": rate,
        "pack_sha256": digest(output / "dwells.pack"),
        "templates_sha256": digest(output / "templates"),
        "reference_build": receipt,
        "reference_build_sha256": digest(receipt_path),
        "source_inputs_sha256": digest(source / "inputs.json"),
        "source_results_sha256": digest(source / "results.json"),
        "records": records,
        "available_dwells": available,
        "selection": f"First at most {maximum} rate-matched dwells in frozen source order, "
        "independent of detector output.",
        "scope": SCOPE,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def _counter(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"0|[1-9][0-9]{0,19}", value)
        or int(value) >= 2**64
    ):
        raise ValueError("noncanonical uint64 counter")
    return int(value)


def _compare(got, expected):
    if isinstance(expected, dict):
        if not isinstance(got, dict) or got.keys() != expected.keys():
            raise ValueError("diagnostic fields differ")
        for key in expected:
            _compare(got[key], expected[key])
    elif isinstance(expected, list):
        if not isinstance(got, list) or len(got) != len(expected):
            raise ValueError("diagnostic inventory differs")
        for a, b in zip(got, expected, strict=True):
            _compare(a, b)
    elif isinstance(expected, int):
        if type(got) is not int or got != expected:
            raise ValueError("diagnostic integer differs")
    elif (
        type(got) not in (float, int)
        or not math.isfinite(got)
        or not math.isfinite(expected)
        or not math.isclose(got, expected, rel_tol=1e-9, abs_tol=1e-10)
    ):
        raise ValueError("diagnostic numerical mismatch")


def verify(raw: str, manifest: dict, duration: int):
    if (
        manifest["schema"] != "org.leo.research.presence-dwell-worker-pack/v1"
        or not 126 <= duration <= 300000
    ):
        raise ValueError("unqualified manifest or duration")
    records, rate = manifest["records"], manifest["rate_hz"]
    if rate not in (2500000, 5000000) or not 1 <= len(records) <= 48:
        raise ValueError("unqualified workload")
    lines = [json.loads(line) for line in raw.splitlines()]
    if not lines or lines[-1]["schema"] != "native-worker-dwell-summary-v1":
        raise ValueError("terminal full-dwell summary missing")
    terminal, rows = lines[-1], lines[:-1]
    jobs = (duration + 125) // 126
    if (
        terminal["rate_hz"] != rate
        or terminal["duration_ms"] != duration
        or terminal["submitted"] != jobs
        or terminal["completed"] != jobs
        or terminal["dropped"] != 0
        or terminal["skipped"] != 0
        or len(rows) != jobs
        or not duration <= terminal["elapsed_ms"] <= duration + 5000
        or not 7200000 < terminal["pool_bytes"] < 7500000
        or not 1 <= terminal["max_occupied_slots"] <= 3
    ):
        raise ValueError("incomplete or incorrectly paced full-dwell workload")
    for seq, row in enumerate(rows):
        p = records[seq % len(records)]
        start = _counter(row["device_counter"])
        if (
            row["schema"] != "native-worker-dwell-result-v1"
            or row["sequence"] != seq
            or row["probe_index"] != seq % len(records)
            or row["status"] != 0
            or row["rx"] != p["rx"]
            or row["rx"] != 1
            or row["rate_hz"] != rate
            or row["visit"] != p["visit"]
            or row["channel"] != p["channel"]
            or row["edge"] != int(p["edge"] == "upper")
            or start != _counter(p["counter"])
            or row["sample_count"] != rate // 50 * 6
            or _counter(row["valid_end"]) != start + rate // 50 * 6
            or row["search_window_mask"] != 63
        ):
            raise ValueError("full-dwell worker identity or coverage differs")
        expected = p["expected"]
        if (
            row["confirmation_window_mask"] != expected["confirmation_window_mask"]
            or row["confirmation_window_mask"] != 1 << row["rank"]["order"][0]
            or len(row["candidates"]) != len(expected["candidates"])
        ):
            raise ValueError("confirmation inventory differs")
        for a, b in zip(row["candidates"], expected["candidates"], strict=True):
            compare_values(a, b)
        compare_values(row["nuisance"], expected["nuisance"], nuisance=True)
        _compare({k: v for k, v in row["rank"].items() if not k.endswith("_ms")}, expected["rank"])
        _compare(row["screen_diagnostics"], expected["screen_diagnostics"])
        for key in (
            "total_cpu_ms",
            "total_wall_ms",
            "confirmation_cpu_ms",
            "confirmation_wall_ms",
            "delivery_latency_ms",
        ):
            if type(row[key]) not in (int, float) or not math.isfinite(row[key]) or row[key] < 0:
                raise ValueError("invalid execution timing")
        for clock in ("cpu", "wall"):
            screen = row["rank"][f"total_{clock}_ms"]
            if (
                not math.isfinite(screen)
                or screen < 0
                or row[f"total_{clock}_ms"] + 1e-5 < screen + row[f"confirmation_{clock}_ms"]
            ):
                raise ValueError("total timing omits full-dwell work")
    return {
        "schema": "org.leo.research.presence-dwell-worker-verification/v1",
        "all_outputs_match_desktop": True,
        "executions": len(rows),
        "terminal": terminal,
        "unique_dwells": len({r["probe_index"] for r in rows}),
        "pack_dwell_count": len(records),
        "timings": {
            key: dict(
                zip(
                    ("p50", "p95", "p99", "max"),
                    np.quantile([r[key] for r in rows], [0.5, 0.95, 0.99, 1]).tolist(),
                    strict=True,
                )
            )
            for key in ("total_cpu_ms", "total_wall_ms", "delivery_latency_ms")
        },
        "limitations": SCOPE
        + " Setup and loading excluded; no RF/IRQ/network contention measured.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare")
    for name in ("source", "output", "library"):
        p.add_argument(name, type=Path)
    p.add_argument("rate", type=int)
    p.add_argument("--maximum", type=int, default=48)
    v = sub.add_parser("verify")
    for name in ("manifest", "raw", "output"):
        v.add_argument(name, type=Path)
    v.add_argument("duration", type=int)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.source, args.output, args.rate, args.library, maximum=args.maximum)
    else:
        safe_output(args.output)
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
