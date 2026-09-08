#!/usr/bin/env python3
"""Freeze/replay development IQ for native parity, without any RF access."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np

from leo.analysis.research.arm_presence import fresh_glrt, noise_control
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from tools.native_presence import ROOT, build_executable, write_probe


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def freeze(root, output):
    output = output.resolve()
    archive = root.resolve()
    if output.is_relative_to(archive) or output.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("experiment outputs cannot be written under capture or QNAP storage")
    output.mkdir(parents=True, exist_ok=False)
    protocol_path = ROOT / "config/analysis/arm-presence-native-v1.json"
    protocol = json.loads(protocol_path.read_text())
    # Bind protocol and numerical source before generating any probe results.
    sources = [ROOT / "src/leo/analysis/research/arm_presence.py"]
    sources += sorted((ROOT / "src/leo/analysis/starlink").glob("*.py"))
    sources += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.c"))
    sources += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.inc"))
    write_json(
        output / "freeze.json",
        {
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "oracle_source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
            "created_unix_ns": time.time_ns(),
            "state": "input_selection_frozen_before_replay",
        },
    )
    rows = []

    def add(name, values, rate, edge, *, counter=0, provenance=None):
        path = output / f"{name}.probe"
        write_probe(path, values, rate, edge, counter)
        started = time.process_time_ns()
        candidates = fresh_glrt(values, rate, edge=edge, candidate_count=2)
        cpu_ms = (time.process_time_ns() - started) / 1e6
        rows.append(
            {
                "file": path.name,
                "sha256": digest(path),
                "rate_hz": rate,
                "edge": edge,
                "device_counter": str(counter),
                "provenance": provenance,
                "oracle_candidates": [asdict(c) for c in candidates],
                "oracle_cpu_ms": cpu_ms,
            }
        )
        print(f"frozen {name}: {len(candidates)} fractional candidates", flush=True)

    store = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(root))
    for session in protocol["sessions"]:
        source = store.source(session["session_id"])
        rate = session["rate_hz"]
        if (
            source.sample_rate_hz != rate
            or source.plan.valid_visit_ms != 120
            or not source.receipt.qualified
        ):
            raise ValueError("archive does not match frozen selection")
        for index in range(
            protocol["first_visit"], protocol["first_visit"] + protocol["visit_count_per_session"]
        ):
            visit = source.read_visit(index)
            samples = visit.complex_samples()[: rate // 50, protocol["receiver"]]
            span = visit.span
            add(
                f"{rate}-{index}",
                samples,
                rate,
                span.target.edge,
                counter=span.valid_device_sample_counter,
                provenance={
                    "session_id": source.session_id,
                    "visit": index,
                    "rx": protocol["receiver"],
                    "manifest_sha256": source.input_manifest_sha256,
                    "input_uri": source.input_uri,
                },
            )
    for rate in protocol["rates_hz"]:
        for edge in protocol["edges"]:
            for kind, seed in (
                ("gaussian", protocol["gaussian_seed"]),
                ("tone_noise", protocol["tone_seed"]),
            ):
                samples = noise_control(rate // 50, rate, seed=seed, kind=kind)
                add(
                    f"{rate}-{edge}-{kind}",
                    samples,
                    rate,
                    edge,
                    counter=10**16 + 23,
                    provenance={"synthetic_kind": kind, "seed": seed},
                )
    write_json(output / "inputs.json", rows)


def compare(candidates, expected, tolerance):
    actual = [c for c in candidates if c["fractional_complete"]]
    if len(actual) != len(expected):
        raise AssertionError("fractional candidate inventory differs")
    for a, e in zip(actual, expected, strict=True):
        if a["epoch"] != e["epoch_sample"] or (a["margin"] >= 0.025) != (e["margin"] >= 0.025):
            raise AssertionError("candidate epoch/order/gate differs")
        for key in ("acquired_cfo_hz", "tracking_cfo_hz"):
            np.testing.assert_allclose(a[key], e[key], rtol=0, atol=tolerance["cfo_atol_hz"])
        np.testing.assert_allclose(
            a["fractional_offset_samples"],
            e["fractional_offset_samples"],
            rtol=0,
            atol=tolerance["fractional_offset_atol_samples"],
        )
        for key in ("exact_score", "margin"):
            np.testing.assert_allclose(
                a[key], e[key], rtol=tolerance["score_rtol"], atol=tolerance["score_atol"]
            )


def replay(output, executable, results):
    protocol = json.loads((output / "freeze.json").read_text())["protocol"]
    inputs = json.loads((output / "inputs.json").read_text())
    evidence = []
    with results.open("x") as stream:
        for probe in inputs:
            path = output / probe["file"]
            if path.name != probe["file"] or digest(path) != probe["sha256"]:
                raise ValueError("probe path or digest mismatch")
            execution = subprocess.run(
                [str(executable), str(path), "3"],
                check=True,
                text=True,
                capture_output=True,
                timeout=95,
            )
            rows = [json.loads(line) for line in execution.stdout.splitlines()]
            if len(rows) != 3:
                raise ValueError("missing replay iterations")
            for row in rows:
                if row["device_counter"] != probe["device_counter"]:
                    raise ValueError("device counter did not survive the replay")
                compare(
                    row["candidates"],
                    probe["oracle_candidates"],
                    protocol["numerical_tolerances_frozen_before_native_results"],
                )
                evidence.append({"probe": probe["file"], **row})
                stream.write(json.dumps(evidence[-1], allow_nan=False) + "\n")
            stream.flush()
            print(f"PASS {probe['file']}: {rows[-1]['total_cpu_ms']:.2f} ms CPU", flush=True)
    write_json(
        results.with_suffix(".summary.json"),
        {
            "host": platform.uname()._asdict(),
            "binary_sha256": digest(executable),
            "inputs_sha256": digest(output / "inputs.json"),
            "probe_count": len(inputs),
            "iteration_count": len(evidence),
            "all_fractional_candidates_match": True,
            "rates": {
                str(rate): {
                    stage: {
                        q: float(
                            np.quantile(
                                [
                                    row[stage]
                                    for row in evidence
                                    if row["rate_hz"] == rate and row["iteration"] > 0
                                ],
                                p,
                            )
                        )
                        for q, p in (("p50", 0.5), ("p95", 0.95), ("p99", 0.99), ("max", 1))
                    }
                    for stage in (
                        "conversion_cpu_ms",
                        "coarse_cpu_ms",
                        "fine_cpu_ms",
                        "fractional_cpu_ms",
                        "total_cpu_ms",
                        "total_wall_ms",
                    )
                }
                for rate in protocol["rates_hz"]
            },
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    frozen = commands.add_parser("freeze")
    frozen.add_argument("output", type=Path)
    frozen.add_argument("--root", type=Path, default=Path("/srv/bulk/leo"))
    build = commands.add_parser("build")
    build.add_argument("output", type=Path)
    build.add_argument("--compiler", default="cc")
    run = commands.add_parser("replay")
    run.add_argument("output", type=Path)
    run.add_argument("executable", type=Path)
    run.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze(args.root, args.output)
    elif args.command == "build":
        build_executable(args.output, compiler=args.compiler)
    else:
        replay(args.output, args.executable.resolve(), args.results)


if __name__ == "__main__":
    main()
