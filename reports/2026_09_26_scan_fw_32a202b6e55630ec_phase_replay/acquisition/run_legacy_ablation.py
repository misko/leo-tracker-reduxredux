#!/usr/bin/env python3
"""Checkpoint one legacy zero-centered sparse acquisition ablation."""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from dataclasses import dataclass
from pathlib import Path

from replay_acquisition import INPUT_MANIFEST_SHA256, SESSION_ID

from leo.scanner.detector import analyze_glrt64_dwell
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


@dataclass(frozen=True)
class SparseConfig:
    dwell_samples: int = 1_200_000
    probe_samples: int = 200_000
    probe_stride_ms: int = 120
    probe_stride_samples: int = 1_200_000
    scheduled_probe_count: int = 1
    sample_rate_hz: int = 10_000_000
    receiver_ids: tuple[int, int] = (0, 1)
    probe_ms: int = 20
    glrt64_margin_gate: float = 0.025
    maximum_acquisition_candidates: int = 8


def run_visit(bulk_root: Path, output: Path, visit_index: int) -> None:
    destination = output / f"visit-{visit_index:06d}.legacy-sparse.json"
    if destination.exists():
        return
    started = time.monotonic()
    store = AdaptiveHopAnalysisInputStore(AdaptiveHopIqStore(bulk_root, read_only=True))
    with store.source(SESSION_ID) as source:
        if source.input_manifest_sha256 != INPUT_MANIFEST_SHA256:
            raise ValueError("source manifest differs from pinned replay")
        samples = source.read_visit(visit_index)
        event = source.visits[visit_index].event
        analysis = analyze_glrt64_dwell(
            samples,
            SparseConfig(),
            edge=event.target.edge,
            search_geometry=None,
        )
    document = {
        "schema": "scan-phase-legacy-zero-centered-sparse-acquisition/v1",
        "visit_index": visit_index,
        "runtime_seconds": time.monotonic() - started,
        "validity_disposition": "raw_equals_rf_valid; no classified invalid rows",
        "analysis": dataclasses.asdict(analysis),
    }
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, sort_keys=True) + "\n")
    temporary.replace(destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("visit_index", type=int)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    run_visit(args.bulk_root, args.output, args.visit_index)


if __name__ == "__main__":
    main()
