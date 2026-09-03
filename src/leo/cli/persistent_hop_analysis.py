"""Low-priority one-shot entrypoint for persistent-hop analysis backfill."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from leo.application.persistent_hop_analysis_v2 import PersistentHopAnalysisServiceV2
from leo.application.persistent_hop_tracking import PersistentHopTrackingService
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.persistent_hop_analysis_v2 import render_persistent_hop_analysis_pngs_v2
from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png
from leo.sky.sites import preset_names, resolve_preset
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore


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
    parser.add_argument(
        "--tle-root",
        type=Path,
        default=Path(os.environ.get("LEO_TLE_ROOT", "/var/lib/leo/tle")),
    )
    parser.add_argument(
        "--site",
        choices=preset_names(),
        required=True,
        help="Reviewed observer-site authority used for causal TLE prediction.",
    )
    parser.add_argument("--maximum-tracking-groups", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()

    captures = PersistentHopIqStore.open_read_only(arguments.bulk_root)
    products = PersistentHopAnalysisStoreV2(arguments.bulk_root)
    tracking_products = PersistentHopTrackingStore(arguments.bulk_root)
    service = PersistentHopAnalysisServiceV2(
        inputs=PersistentHopAnalysisInputStore(captures),
        products=products,
        renderer=render_persistent_hop_analysis_pngs_v2,
        probe_stride_ms=arguments.probe_stride_ms,
        maximum_workers=arguments.maximum_workers,
    )
    preset = resolve_preset(arguments.site)
    observer_site = ObserverSiteV1(
        latitude_deg=preset.latitude_deg,
        longitude_deg=preset.longitude_deg,
        altitude_m=preset.altitude_m,
        label=preset.label,
    )
    tracking = PersistentHopTrackingService(
        captures=captures,
        analyses=products,
        products=tracking_products,
        tle_archive=TleArchiveReader(arguments.tle_root),
        observer_site=observer_site,
        renderer=render_persistent_hop_tracking_png,
        maximum_physical_groups=arguments.maximum_tracking_groups,
    )
    with products.worker_lock() as acquired:
        if not acquired:
            busy_payload = {
                "state": "busy",
                "reason": "persistent-hop analysis worker is active",
            }
            print(
                json.dumps(busy_payload, sort_keys=True)
                if arguments.json
                else busy_payload["reason"]
            )
            return
        result = service.run_pending(
            maximum_sessions=arguments.maximum_sessions,
            session_id=arguments.session_id,
        )
        tracking_result = tracking.run_pending(
            maximum_sessions=arguments.maximum_sessions,
            session_id=arguments.session_id,
        )
    payload: dict[str, object] = {**asdict(result), "tracking": asdict(tracking_result)}
    print(json.dumps(payload, sort_keys=True) if arguments.json else payload)
    if result.failures or tracking_result.failures:
        raise SystemExit(1)
