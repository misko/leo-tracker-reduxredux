"""Bounded shared tracking backfill using existing analyses; never acquires RF."""

import argparse
import json
import os
import time
from pathlib import Path

from leo.application.scanner_tracking import ScannerTrackingService
from leo.contracts.scanner_tracking import ScannerTrackingStatusV1
from leo.contracts.sky import ObserverSiteV1
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png
from leo.sky.sites import preset_names, resolve_preset
from leo.storage.analysis_worker_lock import analysis_worker_lock
from leo.storage.errors import BundleNotFoundError
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, default=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
    )
    parser.add_argument(
        "--tle-root", type=Path, default=Path(os.environ.get("LEO_TLE_ROOT", "/var/lib/leo/tle"))
    )
    parser.add_argument("--site", choices=preset_names(), required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--maximum-seconds", type=float, default=180)
    parser.add_argument("--maximum-sessions", type=int, default=2)
    args = parser.parse_args()
    if not 0 < args.maximum_seconds <= 1800 or not 1 <= args.maximum_sessions <= 100:
        parser.error("invalid work bounds")
    with analysis_worker_lock(args.bulk_root) as acquired:
        if not acquired:
            print(json.dumps({"state": "busy"}))
            return
        sources = ScannerTrackingInputStore(args.bulk_root)
        products = ScannerTrackingStore(args.bulk_root, read_only=False)
        site = resolve_preset(args.site)
        service = ScannerTrackingService(
            inputs=sources,
            products=products,
            tle_archive=TleArchiveReader(args.tle_root),
            observer_site=ObserverSiteV1(
                latitude_deg=site.latitude_deg,
                longitude_deg=site.longitude_deg,
                altitude_m=site.altitude_m,
                label=site.label,
            ),
            renderer=render_persistent_hop_tracking_png,
        )
        try:
            ids = (args.session_id,) if args.session_id else sources.session_ids()
            pending = [
                s
                for s in ids
                if products.status(s).state != "complete"
                and (args.session_id or products.status(s).state != "failed")
            ]
            pending.sort(
                key=lambda s: (products.status(s).state != "running", -sources.captured_at(s))
            )
            started, attempted, failures = time.monotonic(), 0, []
            for sid in pending:
                remaining = args.maximum_seconds - (time.monotonic() - started)
                if remaining <= 0 or attempted >= args.maximum_sessions:
                    break
                try:
                    status = service.run(sid, maximum_seconds=remaining)
                except BundleNotFoundError:
                    continue
                except Exception as error:
                    prior = products.status(sid)
                    products.save(
                        ScannerTrackingStatusV1(
                            session_id=sid,
                            state="failed",
                            phase=prior.phase,
                            product=prior.product,
                            failure_summary=f"{type(error).__name__}: {error}"[:512],
                        )
                    )
                    failures.append(sid)
                else:
                    print(
                        json.dumps(
                            {
                                "session_id": sid,
                                "state": status.state,
                                "trajectory": status.product.trajectory_state
                                if status.product
                                else None,
                                "tle": status.product.tle_state if status.product else None,
                            }
                        ),
                        flush=True,
                    )
                attempted += 1
            if failures:
                raise SystemExit(1)
        finally:
            sources.close()


if __name__ == "__main__":
    main()
