#!/usr/bin/env python3
"""Freeze a wider, preselected archived cohort with dense fractional references."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from leo.analysis.research.arm_presence import fresh_glrt
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from tools.native_presence import ROOT, write_probe
from tools.qualify_native_presence import digest, write_json


def visit_indices(protocol):
    if (
        protocol["receiver"] != 1
        or protocol["targets_per_sweep"] != 8
        or protocol["probe_offset_ms"] != 0
        or protocol["probe_duration_ms"] != 20
        or protocol["reference_candidates"] != 8
    ):
        raise ValueError("unsupported development experiment geometry")
    sweeps = protocol["sweeps"]
    if not sweeps or len(sweeps) > 8 or any(type(s) is not int or s < 0 for s in sweeps):
        raise ValueError("bounded nonnegative sweep indices required")
    if sweeps != sorted(set(sweeps)):
        raise ValueError("sweep indices must be unique and chronological")
    return tuple(s * 8 + target for s in sweeps for target in range(8))


def freeze(archive: Path, output: Path, protocol_path: Path):
    archive, output = archive.resolve(), output.resolve()
    if output.is_relative_to(archive) or output.is_relative_to(Path("/mnt/qnap01")):
        raise ValueError("experiment output cannot be beneath capture or QNAP storage")
    protocol = json.loads(protocol_path.read_text())
    indices = visit_indices(protocol)
    output.mkdir(parents=True, exist_ok=False)
    store = PersistentHopAnalysisInputStore(PersistentHopIqStore.open_read_only(archive))
    sources = []
    for spec in protocol["sessions"]:
        source = store.source(spec["session_id"])
        if (
            source.sample_rate_hz != spec["rate_hz"]
            or source.sample_rate_hz not in (2500000, 5000000)
            or source.plan.valid_visit_ms != 120
            or not source.receipt.qualified
            or 1 not in source.receiver_ids
            or indices[-1] >= len(source.visits)
        ):
            raise ValueError("source does not match the frozen experiment")
        sources.append(source)
    numerical_files = sorted((ROOT / "src/leo/analysis/starlink").glob("*.py"))
    numerical_files += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.c"))
    numerical_files += sorted((ROOT / "src/leo/analysis/starlink").glob("*acquisition*.inc"))
    numerical_files += [ROOT / "src/leo/analysis/research/arm_presence.py", Path(__file__)]
    write_json(
        output / "freeze.json",
        {
            "schema": "org.leo.research.arm-presence-wide-development-freeze/v1",
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "source_manifests": {s.session_id: s.input_manifest_sha256 for s in sources},
            "numerical_sources": {str(p.relative_to(ROOT)): digest(p) for p in numerical_files},
            "state": "selection_and_sources_frozen_before_scoring",
        },
    )
    rows = []
    for source in sources:
        rate = source.sample_rate_hz
        for index in indices:
            visit = source.read_visit(index)
            samples = visit.complex_samples()[: rate // 50, source.receiver_ids.index(1)]
            counter = visit.span.valid_device_sample_counter
            path = output / f"{rate}-{index}.probe"
            write_probe(path, samples, rate, visit.span.target.edge, counter)
            reference = fresh_glrt(samples, rate, edge=visit.span.target.edge, candidate_count=8)
            rows.append(
                {
                    "file": path.name,
                    "sha256": digest(path),
                    "rate_hz": rate,
                    "edge": visit.span.target.edge,
                    "device_counter": str(counter),
                    "provenance": {
                        "session_id": source.session_id,
                        "visit": index,
                        "rx": 1,
                        "manifest_sha256": source.input_manifest_sha256,
                        "input_uri": source.input_uri,
                    },
                    "oracle_candidates": [asdict(c) for c in reference],
                }
            )
            print(
                path.name,
                "dense passing candidates",
                sum(c.margin >= protocol["reference_margin"] for c in reference),
                flush=True,
            )
    write_json(output / "inputs.json", rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=ROOT / "config/analysis/arm-presence-wide-development-v1.json",
    )
    args = parser.parse_args()
    freeze(args.archive, args.output, args.protocol)


if __name__ == "__main__":
    main()
