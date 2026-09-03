"""Low-priority one-shot entrypoint for persistent-hop analysis backfill."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from leo.application.persistent_hop_analysis import PersistentHopAnalysisService
from leo.presentation.persistent_hop_analysis import render_persistent_hop_analysis_pngs
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis import PersistentHopAnalysisStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root",
        type=Path,
        default=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo")),
    )
    parser.add_argument("--maximum-sessions", type=int, default=1)
    parser.add_argument(
        "--probe-stride-ms",
        type=int,
        choices=(10, 20, 40, 60, 120),
        default=120,
        help=(
            "Persisted temporal sampling stride; 10 ms is exhaustive and "
            "120 ms is one probe per visit."
        ),
    )
    parser.add_argument("--session-id")
    parser.add_argument("--maximum-workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()

    captures = PersistentHopIqStore.open_read_only(arguments.bulk_root)
    products = PersistentHopAnalysisStore(arguments.bulk_root)
    service = PersistentHopAnalysisService(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=products,
        renderer=render_persistent_hop_analysis_pngs,
        probe_stride_ms=arguments.probe_stride_ms,
        maximum_workers=arguments.maximum_workers,
    )
    with products.worker_lock() as acquired:
        if not acquired:
            payload = {"state": "busy", "reason": "persistent-hop analysis worker is active"}
            print(json.dumps(payload, sort_keys=True) if arguments.json else payload["reason"])
            return
        result = service.run_pending(
            maximum_sessions=arguments.maximum_sessions,
            session_id=arguments.session_id,
        )
    payload = asdict(result)
    print(json.dumps(payload, sort_keys=True) if arguments.json else payload)
    if result.failures:
        raise SystemExit(1)
