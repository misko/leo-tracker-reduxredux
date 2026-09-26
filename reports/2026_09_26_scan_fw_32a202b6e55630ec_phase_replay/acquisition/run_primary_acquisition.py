#!/usr/bin/env python3
"""Checkpointed corrected six-probe acquisition for the sealed primary cohort."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from replay_acquisition import (
    INPUT_MANIFEST_SHA256,
    PINNED_REPLAY_REVISION,
    SESSION_ID,
)

from leo.scanner.adaptive_hop_analysis import (
    VariableDwellAnalysisConfigurationV5,
    analyze_adaptive_hop_visit,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore


def run_visit(bulk_root: Path, output: Path, visit_index: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"visit-{visit_index:06d}.corrected-dense.json"
    if destination.exists():
        return
    started = time.monotonic()
    store = AdaptiveHopAnalysisInputStore(AdaptiveHopIqStore(bulk_root, read_only=True))
    with store.source(SESSION_ID) as source:
        if source.input_manifest_sha256 != INPUT_MANIFEST_SHA256:
            raise ValueError("source manifest differs from pinned replay")
        product = analyze_adaptive_hop_visit(
            source,
            visit_index,
            configuration=VariableDwellAnalysisConfigurationV5(
                sample_rate_hz=10_000_000,
                probe_stride_ms=20,
            ),
        )
    document = {
        "schema": "scan-phase-corrected-dense-acquisition/v1",
        "pinned_replay_revision": PINNED_REPLAY_REVISION,
        "input_manifest_sha256": INPUT_MANIFEST_SHA256,
        "visit_index": visit_index,
        "runtime_seconds": time.monotonic() - started,
        "validity_disposition": (
            "raw_equals_rf_valid: capture audit found no classified invalid rows in this visit; "
            "no zero filling or interpolation"
        ),
        "frequency_coordinate_semantics": {
            "acquired_cfo_hz": "absolute tuner-baseband mixer coordinate",
            "fractional_residual_cfo_hz": "GLRT residual relative to acquired coordinate",
            "fractional_tracking_cfo_hz": "absolute tuner-baseband acquired plus residual",
            "display_coordinate": (
                "derive pilot-relative canonical CFO separately; never mix IQ with it"
            ),
        },
        "product": product.model_dump(mode="json"),
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
    run_visit(args.bulk_root, args.output, args.visit_index)


if __name__ == "__main__":
    main()
