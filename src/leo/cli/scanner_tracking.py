"""Bounded shared tracking backfill using existing analyses; never acquires RF."""

import argparse
import json
import os
import time
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from leo.application.scanner_tracking import ScannerTrackingService
from leo.contracts.scanner_tracking import (
    ArtifactName,
    ScannerTleReviewCandidateV1,
    ScannerTleTrackReviewV1,
    ScannerTrackingStatusV11,
)
from leo.contracts.sky import ObserverSiteV1
from leo.operations.scanner_tle_review_report import build_report
from leo.operations.tle_archive import TleArchiveReader
from leo.presentation.persistent_hop_tracking import render_persistent_hop_tracking_png
from leo.sky.sites import preset_names, resolve_preset
from leo.storage.analysis_worker_lock import analysis_worker_lock
from leo.storage.errors import BundleNotFoundError
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def _review_renderer(*, bulk_root: Path, tle_root: Path, site_name: str):
    def render(session_id: str) -> tuple[tuple[ScannerTleTrackReviewV1, bytes], ...]:
        with TemporaryDirectory(prefix="leo-tle-review-") as temporary:
            output = Path(temporary)
            report = build_report(
                session_id,
                output,
                bulk_root=bulk_root,
                tle_root=tle_root,
                site_name=site_name,
                maximum_tracks=32,
            )
            rendered = []
            for index, (track, filename) in enumerate(
                zip(report["tracks"], report["track_figures"], strict=True), start=1
            ):
                if index > 32:
                    raise ValueError("track review artifact count exceeds contract bound")
                artifact_name = cast(ArtifactName, f"tle-review-{index:02d}")
                review = ScannerTleTrackReviewV1(
                    tracklet_id=track["tracklet_id"],
                    channel=track["channel"],
                    edge=track["edge"],
                    start_s=track["start_s"],
                    end_s=track["end_s"],
                    observation_count=track["observation_count"],
                    fit_observation_count=track["training_count"],
                    randomized_evaluation_observation_count=track["heldout_count"],
                    artifact_name=artifact_name,
                    candidates=tuple(
                        ScannerTleReviewCandidateV1(
                            rank=item["standard_rank"],
                            catalog_number=item["catalog_number"],
                            selected_tau_s=item["selected_tau_s"],
                            fitted_offset_hz=item["offset_hz"],
                            fit_rms_hz=item["offset_only_training_rms_hz"],
                            randomized_evaluation_rms_hz=item["offset_only_heldout_rms_hz"],
                        )
                        for item in track["candidates"]
                    ),
                )
                rendered.append((review, (output / filename).read_bytes()))
            return tuple(rendered)

    return render


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
    parser.add_argument(
        "--queue-worker",
        action="store_true",
        help="The processing queue owns the session lease; do not take the standalone lock.",
    )
    args = parser.parse_args()
    if not 0 < args.maximum_seconds <= 1800 or not 1 <= args.maximum_sessions <= 100:
        parser.error("invalid work bounds")
    lock = nullcontext(True) if args.queue_worker else analysis_worker_lock(args.bulk_root)
    with lock as acquired:
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
            review_renderer=_review_renderer(
                bulk_root=args.bulk_root,
                tle_root=args.tle_root,
                site_name=args.site,
            ),
        )
        try:
            ids = (args.session_id,) if args.session_id else sources.session_ids()
            pending = [
                s
                for s in ids
                if products.analysis_status(s).state != "complete"
                and (args.session_id or products.analysis_status(s).state != "failed")
            ]
            pending.sort(
                key=lambda s: (
                    products.analysis_status(s).state != "running",
                    -sources.captured_at(s),
                )
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
                    prior = products.analysis_status(sid)
                    products.save(
                        ScannerTrackingStatusV11(
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
