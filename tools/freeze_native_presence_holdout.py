#!/usr/bin/env python3
"""Freeze bounded, previously unused scan excerpts and native/reference outputs."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path

from leo.analysis.research.arm_presence import fresh_glrt
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from tools.evaluate_native_presence_budgets import associated
from tools.native_presence import NATIVE, ROOT, build_executable, write_probe
from tools.qualify_native_presence import digest, write_json


def selection(protocol):
    if (
        protocol["schema"] != "org.leo.research.arm-presence-holdout/v1"
        or protocol["receiver"] != 1
        or protocol["targets_per_sweep"] != 8
        or protocol["probe_duration_ms"] != 20
        or protocol["probe_offsets_ms"] != list(range(0, 120, 20))
        or protocol["reference_candidates"] != 8
        or protocol["reference_margin"] != 0.025
    ):
        raise ValueError("unreviewed holdout geometry")
    sweeps = protocol["sweeps"]
    sessions = protocol["sessions"]
    if (
        not 1 <= len(sweeps) <= 4
        or any(type(s) is not int or not 0 <= s < 290 for s in sweeps)
        or sweeps != sorted(set(sweeps))
        or len(sessions) != 4
        or len({s["session_id"] for s in sessions}) != 4
        or sorted(s["rate_hz"] for s in sessions) != [2500000, 2500000, 5000000, 5000000]
        or {s["session_id"] for s in sessions}.intersection(
            protocol["excluded_previously_examined_sessions"]
        )
    ):
        raise ValueError("holdout selection must be bounded, unused, and rate balanced")
    return tuple(s * 8 + t for s in sweeps for t in range(8))


def local_counter(counter, rate, offset_ms):
    if type(counter) is not int or counter < 0 or rate not in (2500000, 5000000):
        raise ValueError("invalid counter or rate")
    if type(offset_ms) is not int or offset_ms not in range(0, 120, 20):
        raise ValueError("offset outside the frozen tiling")
    result = counter + rate * offset_ms // 1000
    if result + rate // 50 >= 2**64:
        raise ValueError("probe counter interval overflows uint64")
    return result


def freeze(archive: Path, output: Path, protocol_path: Path):
    archive, output = archive.resolve(), output.resolve()
    if output.is_relative_to(archive) or output.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("holdout output cannot be beneath archive storage")
    protocol = json.loads(protocol_path.read_text())
    indices = selection(protocol)
    detector_path = (ROOT / protocol["detector_protocol"]).resolve()
    if not detector_path.is_relative_to(ROOT / "config/analysis"):
        raise ValueError("detector protocol is outside the reviewed configuration directory")
    detector = json.loads(detector_path.read_text())
    if (
        len(detector["variants"]) != 1
        or detector["variants"][0]["name"] != "diff4_staged_tone_ci16"
    ):
        raise ValueError("holdout requires the frozen single detector")
    output.mkdir(parents=True, exist_ok=False)
    store = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(archive))
    sources = [store.source(spec["session_id"]) for spec in protocol["sessions"]]
    for spec, source in zip(protocol["sessions"], sources, strict=True):
        if (
            source.sample_rate_hz != spec["rate_hz"]
            or source.plan.valid_visit_ms != 120
            or not source.receipt.qualified
            or 1 not in source.receiver_ids
            or indices[-1] >= len(source.visits)
        ):
            raise ValueError("source differs from frozen holdout selection")
    numerical = sorted((ROOT / "src/leo/analysis/starlink").glob("*.py"))
    numerical += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.c"))
    numerical += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.inc"))
    numerical += sorted(NATIVE.glob("*.[ch]"))
    numerical += [ROOT / "src/leo/analysis/research/arm_presence.py", Path(__file__)]
    hashes = {str(p.relative_to(ROOT)): digest(p) for p in numerical}
    write_json(
        output / "freeze.json",
        {
            "schema": "org.leo.research.arm-presence-holdout-freeze/v1",
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "detector_protocol_sha256": digest(detector_path),
            "source_manifests": {s.session_id: s.input_manifest_sha256 for s in sources},
            "numerical_sources": hashes,
            "state": "frozen_before_iq_read_or_scoring",
        },
    )
    variant = detector["variants"][0]
    flags = tuple(detector["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in variant["defines"].items()
    )
    binary = build_executable(output / variant["name"], cflags=flags)
    rows, results = [], []
    for source in sources:
        rate = source.sample_rate_hz
        for index in indices:
            visit = source.read_visit(index)
            values = visit.complex_samples()[:, source.receiver_ids.index(1)]
            for offset in protocol["probe_offsets_ms"]:
                counter = local_counter(visit.span.valid_device_sample_counter, rate, offset)
                start = rate * offset // 1000
                samples = values[start : start + rate // 50]
                path = output / f"{source.session_id}-{index}-{offset}.probe"
                write_probe(path, samples, rate, visit.span.target.edge, counter, ci16=True)
                reference = fresh_glrt(
                    samples, rate, edge=visit.span.target.edge, candidate_count=8
                )
                evidence = json.loads(
                    subprocess.run(
                        [str(binary), str(path), "1", "--nuisance"],
                        check=True,
                        text=True,
                        capture_output=True,
                        timeout=95,
                    ).stdout
                )
                if (
                    evidence["device_counter"] != str(counter)
                    or evidence["format"] != 2
                    or evidence["rate_hz"] != rate
                    or evidence["edge"] != int(visit.span.target.edge == "upper")
                ):
                    raise ValueError("native holdout result identity mismatch")
                provenance = {
                    "session_id": source.session_id,
                    "visit": index,
                    "rx": 1,
                    "probe_offset_ms": offset,
                    "manifest_sha256": source.input_manifest_sha256,
                    "input_uri": source.input_uri,
                    "channel": visit.span.target.channel,
                }
                rows.append(
                    {
                        "file": path.name,
                        "sha256": digest(path),
                        "rate_hz": rate,
                        "edge": visit.span.target.edge,
                        "device_counter": str(counter),
                        "provenance": provenance,
                        "oracle_candidates": [asdict(c) for c in reference],
                    }
                )
                positive = [asdict(c) for c in reference if c.margin >= 0.025]
                detected = [
                    c
                    for c in evidence["candidates"]
                    if c["fractional_complete"] and c["margin"] >= 0.025
                ]
                results.append(
                    {
                        "variant": variant["name"],
                        "probe": path.name,
                        "binary_sha256": digest(binary),
                        "provenance": provenance,
                        "reference_positive": bool(positive),
                        "detected": bool(detected),
                        "matched_reference": any(
                            associated(a, b, rate, detector["reference_association"])
                            for a in detected
                            for b in positive
                        ),
                        "result": evidence,
                    }
                )
            print(source.session_id, "visit", index, "six windows scored", flush=True)
    if hashes != {str(p.relative_to(ROOT)): digest(p) for p in numerical}:
        raise RuntimeError("numerical sources changed during holdout scoring")
    write_json(output / "inputs.json", rows)
    write_json(output / "results.json", results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--protocol", type=Path, default=ROOT / "config/analysis/arm-presence-holdout-v1.json"
    )
    args = parser.parse_args()
    freeze(args.archive, args.output, args.protocol)


if __name__ == "__main__":
    main()
