"""Publish a reviewed adaptive dual-RX phase PNG against sealed GLRT metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import TypeAdapter

from leo.scanner.adaptive_hop import SessionId
from leo.storage.adaptive_dual_rx_phase import AdaptiveDualRxPhaseStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore


def _count(text: str) -> int:
    value = int(text)
    if not 0 <= value <= 5000:
        raise argparse.ArgumentTypeError("count must be in 0..5000")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--qualified-phase-count", type=_count, required=True)
    parser.add_argument("--association-count", type=_count, required=True)
    parser.add_argument("--probe-stride-ms", type=int, choices=(10, 120), default=120)
    args = parser.parse_args()
    try:
        TypeAdapter(SessionId).validate_python(args.session_id)
        presentation = AdaptiveHopAnalysisPresentationStore(args.bulk_root)
        analysis = presentation.status(args.session_id, probe_stride_ms=args.probe_stride_ms)
        if analysis is None:
            raise ValueError("adaptive session does not exist")
        if tuple(analysis.configuration.receiver_ids) != (0, 1):
            raise ValueError("phase publication requires simultaneous RX0 and RX1")
        if analysis.metrics_manifest_sha256 is None:
            raise ValueError("phase publication requires sealed GLRT metrics")
        payload = args.png.read_bytes()
        store = AdaptiveDualRxPhaseStore(args.bulk_root)
        try:
            manifest = store.publish(
                session_id=args.session_id,
                input_manifest_sha256=analysis.input_manifest_sha256,
                glrt_binding_sha256=analysis.binding_sha256,
                glrt_metrics_manifest_sha256=analysis.metrics_manifest_sha256,
                qualified_phase_count=args.qualified_phase_count,
                association_count=args.association_count,
                png=payload,
            )
        finally:
            store.close()
        print(json.dumps(manifest.model_dump(mode="json"), sort_keys=True))
    except Exception as error:
        print(
            json.dumps(
                {"state": "failed", "error_type": type(error).__name__, "message": str(error)[:512]}
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
