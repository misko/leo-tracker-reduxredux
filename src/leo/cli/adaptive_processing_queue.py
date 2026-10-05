"""Schedule and execute adaptive scanner analysis in the shared processing queue."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.catalog.errors import LeaseLostError
from leo.cli.adaptive_tle_position import adaptive_tle_position_complete
from leo.cli.blind_regional import blind_regional_complete
from leo.cli.job_lease import LeaseSupervisor, run_process
from leo.cli.scan_position_methods import position_methods_complete
from leo.contracts.digests import canonical_digest
from leo.contracts.partial_band import PartialBandConfigurationV1, partial_band_identity
from leo.scanner.adaptive_hop import AdaptiveHopReceiptV8
from leo.sky.sites import resolve_preset
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.errors import BundleNotFoundError
from leo.storage.partial_band import PartialBandStore
from leo.storage.scanner_tracking import ScannerTrackingStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

_LEASE = timedelta(minutes=20)
_SLICE_SECONDS = 560
_TRACKING_SITE = "spinnaker-sausalito"
_TRACKING_GROUP_LIMIT = 4


def _position_methods_complete(
    bulk_root: Path, session_id: str, *, expected_input_manifest_sha256: str
) -> bool:
    try:
        legacy_complete = position_methods_complete(
            bulk_root,
            session_id,
            expected_input_manifest_sha256=expected_input_manifest_sha256,
        ) and blind_regional_complete(
            bulk_root,
            session_id,
            expected_input_manifest_sha256=expected_input_manifest_sha256,
        )
        if not legacy_complete:
            return False
        if not adaptive_tle_position_complete(
            bulk_root,
            session_id,
            expected_input=expected_input_manifest_sha256,
        ):
            return False
        sources = ScannerTrackingInputStore(bulk_root)
        try:
            source = sources.load(session_id)
        finally:
            sources.close()
        return adaptive_tle_position_complete(
            bulk_root,
            session_id,
            expected_input=expected_input_manifest_sha256,
            expected_analysis=source.analysis_manifest_sha256,
        )
    except (BundleNotFoundError, OSError, ValueError):
        return False


def _catalog() -> CatalogRepository:
    database_url = os.environ.get("LEO_DATABASE_URL")
    if not database_url:
        raise RuntimeError("LEO_DATABASE_URL is required")
    return CatalogRepository(create_session_factory(create_catalog_engine(database_url)))


def _worker_catalog() -> tuple[CatalogRepository, Engine]:
    """Create the single bounded database pool owned by one worker process."""
    database_url = os.environ.get("LEO_DATABASE_URL")
    if not database_url:
        raise RuntimeError("LEO_DATABASE_URL is required")
    url = make_url(database_url)
    prior_options = str(url.query.get("options", ""))
    url = url.update_query_dict(
        {
            "connect_timeout": "10",
            "options": f"{prior_options} -c statement_timeout=10000 -c lock_timeout=5000".strip(),
            "tcp_user_timeout": "15000",
        }
    )
    engine = create_catalog_engine(
        url.render_as_string(hide_password=False), pool_size=1, max_overflow=0
    )
    return CatalogRepository(create_session_factory(engine)), engine


def _tracking_digest(*, capture, metrics_manifest_sha256: str, site: str) -> str:
    preset = resolve_preset(site)
    return canonical_digest(
        {
            "analysis_id": "scanner-shared-tracking-v15",
            "position": "scanner-conditional-position-v1",
            "additional_position_methods": "scanner-position-methods-v1",
            "blind_association_and_position": "scanner-blind-regional-v1",
            "adaptive_tle_position": "scanner-adaptive-tle-position-v2",
            "trajectory_minimum_span_s": 4.0,
            "tle_minimum_support_observations": 14,
            "tle_minimum_support_span_s": 7.0,
            "trajectory_maximum_gap_s": 4.0,
            "utc_qualification_limit_ns": 2_000_000_000,
            "capture_manifest": capture.manifest_sha256,
            "metrics_manifest": metrics_manifest_sha256,
            "observer_site": preset.model_dump(mode="json"),
            "group_limit": _TRACKING_GROUP_LIMIT,
            "review_limit": 64,
            "review_selection_policy": "longest-support-observations-identity-v1",
            "tle_residual_partition": "deterministic-randomized-observation-v1",
            "control_comparison": "minimum-0.01-nll-per-evaluation-observation-v1",
            "association_gates": "nominal-catalogue-only-v1",
            "catalogue": "exclude-labelled-debris-and-sgp4-failures-before-response-v1",
            "propagation_screen": "capture-and-control-boundaries-v1",
        }
    )


def _capture_allowed(capture) -> bool:
    """Preserve the deployed capture-time cutoff, never substituting import time."""
    minimum = os.environ.get("LEO_ADAPTIVE_MIN_CAPTURE_UTC_NS")
    if not minimum:
        return True
    cutoff = int(minimum)
    if cutoff < 0:
        raise ValueError("adaptive minimum capture timestamp must be non-negative")
    timing = capture.manifest.timing
    return timing is not None and timing.first_sample_estimate_utc_ns >= cutoff


def enqueue_pending(*, bulk_root: Path, site: str = _TRACKING_SITE) -> tuple[str, ...]:
    """Enqueue missing metrics and tracking for captures from the live window."""
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    tracking = ScannerTrackingStore(bulk_root, read_only=True)
    catalog = _catalog()
    queued: list[str] = []
    try:
        queued_sessions = catalog.adaptive_job_kinds_by_session()
        recent_cutoff = time.time_ns() - 2 * 3600 * 10**9
        for indexed_utc_ns, session_id in captures.publication_index():
            # Cadence owns only the bounded live window. Historical repair is an
            # explicit backfill operation and must not make every timer tick walk
            # large legacy analysis trees.
            if indexed_utc_ns < recent_cutoff:
                continue
            # A queue job owns retries and enqueues tracking after analysis. Capture
            # publications are immutable, so reopening an already-owned session on
            # every cadence tick cannot discover new work.
            if queued_sessions.get(session_id):
                continue
            capture = captures.inspect(session_id)
            if not _capture_allowed(capture):
                continue
            if isinstance(capture.manifest.receipt, AdaptiveHopReceiptV8):
                status = PartialBandStore(bulk_root).status(session_id, capture.manifest_sha256)
                if status.state != "figures_ready" and catalog.enqueue_adaptive_analysis_job(
                    session_id=session_id,
                    input_manifest_digest=capture.manifest_sha256,
                    configuration_digest=status.binding_sha256,
                    priority=100,
                    resource_class="heavy",
                ):
                    queued.append(session_id)
                continue
            status = presentation.status_for_capture(capture, probe_stride_ms=120)
            priority = 100 if capture.manifest.created_utc_ns > recent_cutoff else 0
            phase_pending = False
            if status.state == "figures_ready" and indexed_utc_ns >= recent_cutoff:
                relative_phase = presentation.relative_phase_status(session_id, probe_stride_ms=120)
                phase_pending = relative_phase is None or relative_phase.state == "pending"
            if status.state != "figures_ready" or phase_pending:
                if catalog.enqueue_adaptive_analysis_job(
                    session_id=session_id,
                    input_manifest_digest=capture.manifest_sha256,
                    configuration_digest=canonical_digest(
                        {
                            "metrics": status.binding_sha256,
                            "relative_phase": "adaptive-broadband-pilot-relative-phase-v1",
                        }
                    ),
                    priority=priority,
                    resource_class="heavy",
                ):
                    queued.append(session_id)
                    queued_sessions[session_id] = frozenset(("adaptive_scan",))
                continue
            if status.metrics_manifest_sha256 is None:
                raise ValueError("figures-ready adaptive analysis lacks metrics authority")
            if tracking.analysis_status(
                session_id
            ).state == "complete" and _position_methods_complete(
                bulk_root,
                session_id,
                expected_input_manifest_sha256=capture.manifest_sha256,
            ):
                continue
            if catalog.enqueue_adaptive_tracking_job(
                session_id=session_id,
                input_manifest_digest=capture.manifest_sha256,
                configuration_digest=_tracking_digest(
                    capture=capture,
                    metrics_manifest_sha256=status.metrics_manifest_sha256,
                    site=site,
                ),
                priority=priority,
            ):
                queued.append(session_id)
                queued_sessions[session_id] = frozenset(("adaptive_tracking",))
    finally:
        captures.close()
    return tuple(queued)


def enqueue_tracking_backfill(
    *,
    bulk_root: Path,
    site: str = _TRACKING_SITE,
    limit: int = 100,
    since_utc_ns: int | None = None,
    until_utc_ns: int | None = None,
) -> tuple[str, ...]:
    """Boundedly enqueue missing tracking for already-complete adaptive metrics."""
    if limit < 1:
        raise ValueError("backfill limit must be positive")
    if since_utc_ns is not None and since_utc_ns < 0:
        raise ValueError("backfill since timestamp must be non-negative")
    if until_utc_ns is not None and until_utc_ns < 0:
        raise ValueError("backfill until timestamp must be non-negative")
    if since_utc_ns is not None and until_utc_ns is not None and since_utc_ns > until_utc_ns:
        raise ValueError("backfill since timestamp must not exceed until timestamp")
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    tracking = ScannerTrackingStore(bulk_root, read_only=True)
    catalog = _catalog()
    queued: list[str] = []
    try:
        for indexed_utc_ns, session_id in reversed(captures.publication_index()):
            if since_utc_ns is not None and indexed_utc_ns < since_utc_ns:
                continue
            if until_utc_ns is not None and indexed_utc_ns > until_utc_ns:
                continue
            capture = captures.inspect(session_id)
            if not _capture_allowed(capture):
                continue
            if isinstance(capture.manifest.receipt, AdaptiveHopReceiptV8):
                print(
                    json.dumps(
                        {"session_id": session_id, "analysis": "unsupported_native_1p25_rate"}
                    )
                )
                continue
            status = presentation.status_for_capture(capture, probe_stride_ms=120)
            if status.state != "figures_ready" or status.metrics_manifest_sha256 is None:
                continue
            if tracking.analysis_status(
                session_id
            ).state == "complete" and _position_methods_complete(
                bulk_root,
                session_id,
                expected_input_manifest_sha256=capture.manifest_sha256,
            ):
                continue
            if catalog.enqueue_adaptive_tracking_job(
                session_id=session_id,
                input_manifest_digest=capture.manifest_sha256,
                configuration_digest=_tracking_digest(
                    capture=capture,
                    metrics_manifest_sha256=status.metrics_manifest_sha256,
                    site=site,
                ),
            ):
                queued.append(session_id)
                if len(queued) >= limit:
                    break
    finally:
        captures.close()
    return tuple(queued)


def _command_for_lease(*, lease, bulk_root: Path, site: str) -> list[str]:
    if _partial_band_lease(lease):
        return [
            sys.executable,
            "-m",
            "leo.cli.partial_band",
            "--bulk-root",
            str(bulk_root),
            "--session-id",
            lease.session_id,
            "--maximum-workers",
            "1",
            "--maximum-seconds",
            str(_SLICE_SECONDS),
        ]
    if lease.job_kind == "adaptive_scan":
        return [
            sys.executable,
            "-m",
            "leo.cli.adaptive_hop_analysis",
            "--bulk-root",
            str(bulk_root),
            "--session-id",
            lease.session_id,
            "--maximum-workers",
            "2",
            "--host-maximum-workers",
            "2",
            "--probe-stride-ms",
            "120",
            "--maximum-visits",
            "2500",
            "--maximum-seconds",
            str(_SLICE_SECONDS),
        ]
    if lease.job_kind == "adaptive_tracking":
        return [
            sys.executable,
            "-m",
            "leo.cli.scanner_tracking",
            "--bulk-root",
            str(bulk_root),
            "--site",
            site,
            "--session-id",
            lease.session_id,
            "--maximum-seconds",
            str(_SLICE_SECONDS),
            "--maximum-sessions",
            "1",
            "--review-limit",
            "64",
            "--queue-worker",
        ]
    raise ValueError(f"unsupported adaptive queue job kind: {lease.job_kind}")


def _partial_band_lease(lease) -> bool:
    return lease.job_kind == "adaptive_scan" and getattr(
        lease, "configuration_digest", None
    ) == partial_band_identity(
        lease.session_id,
        getattr(lease, "input_manifest_digest", None),
        PartialBandConfigurationV1(),
    )


def _last_json(stdout: str) -> dict[str, object]:
    payloads = [json.loads(line) for line in stdout.splitlines() if line.lstrip().startswith("{")]
    return payloads[-1] if payloads else {}


def _enqueue_tracking_after_analysis(
    *,
    bulk_root: Path,
    session_id: str,
    site: str,
    catalog: CatalogRepository,
) -> bool:
    """Queue tracking from sealed metrics without applying the live-window cutoff."""
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    tracking = ScannerTrackingStore(bulk_root, read_only=True)
    try:
        capture = captures.inspect(session_id)
        if not _capture_allowed(capture):
            return False
        status = presentation.status_for_capture(capture, probe_stride_ms=120)
        if status.state != "figures_ready" or status.metrics_manifest_sha256 is None:
            raise ValueError("completed adaptive analysis lacks sealed overview authority")
        if tracking.analysis_status(session_id).state == "complete" and _position_methods_complete(
            bulk_root,
            session_id,
            expected_input_manifest_sha256=capture.manifest_sha256,
        ):
            return False
        return catalog.enqueue_adaptive_tracking_job(
            session_id=session_id,
            input_manifest_digest=capture.manifest_sha256,
            configuration_digest=_tracking_digest(
                capture=capture,
                metrics_manifest_sha256=status.metrics_manifest_sha256,
                site=site,
            ),
            priority=(
                100 if capture.manifest.created_utc_ns > time.time_ns() - 2 * 3600 * 10**9 else 0
            ),
        )
    finally:
        captures.close()


def run_once(
    *,
    bulk_root: Path,
    worker_id: str,
    catalog: CatalogRepository | None = None,
    site: str = _TRACKING_SITE,
) -> bool:
    catalog = _catalog() if catalog is None else catalog
    lease = catalog.claim_adaptive_job(worker_id=worker_id, lease_for=_LEASE)
    if lease is None:
        return False
    with LeaseSupervisor(catalog, lease, lease_for=_LEASE) as supervisor:
        try:
            return _run_claimed(
                bulk_root=bulk_root,
                worker_id=worker_id,
                catalog=supervisor,
                site=site,
                lease=lease,
            )
        except KeyboardInterrupt:
            with suppress(LeaseLostError):
                supervisor.yield_adaptive_analysis_job(job_id=lease.job_id, worker_id=worker_id)
            raise


def _run_claimed(*, bulk_root, worker_id, catalog, site, lease):
    if lease.job_kind == "adaptive_tracking":
        tracking_status = ScannerTrackingStore(bulk_root, read_only=True).analysis_status(
            lease.session_id
        )
        if tracking_status.state == "complete" and _position_methods_complete(
            bulk_root,
            lease.session_id,
            expected_input_manifest_sha256=lease.input_manifest_digest,
        ):
            catalog.complete_job(
                job_id=lease.job_id,
                worker_id=worker_id,
                outcome="already_complete",
            )
            return True
    command = _command_for_lease(lease=lease, bulk_root=bulk_root, site=site)
    try:
        completed = run_process(command, supervisor=catalog)
    except subprocess.TimeoutExpired:
        catalog.fail_job(
            job_id=lease.job_id,
            worker_id=worker_id,
            error="analysis exceeded two-hour execution watchdog",
            retryable=True,
            retry_after=timedelta(minutes=2),
        )
        return True
    payload = _last_json(completed.stdout)
    if completed.returncode or payload.get("state") == "failed":
        catalog.fail_job(
            job_id=lease.job_id,
            worker_id=worker_id,
            error=(completed.stderr or completed.stdout)[-1024:],
            retryable=True,
            retry_after=timedelta(minutes=2),
        )
    elif _partial_band_lease(lease) and payload.get("state") == "figures_ready":
        try:
            status = PartialBandStore(bulk_root).status(
                lease.session_id, lease.input_manifest_digest
            )
            if (
                status.state != "figures_ready"
                or status.binding_sha256 != lease.configuration_digest
            ):
                raise ValueError("low-rate worker lacks verified complete artifact authority")
        except (ValueError, OSError) as error:
            catalog.fail_job(
                job_id=lease.job_id,
                worker_id=worker_id,
                error=str(error)[:1024],
                retryable=True,
                retry_after=timedelta(minutes=2),
            )
        else:
            catalog.complete_job(job_id=lease.job_id, worker_id=worker_id, outcome="complete")
    elif (
        lease.job_kind == "adaptive_scan"
        and payload.get("state") == "metrics_complete"
        and payload.get("overview_state") == "ready"
        and payload.get("relative_phase_state") == "complete"
    ) or (
        lease.job_kind == "adaptive_tracking"
        and payload.get("state") == "complete"
        and payload.get("position_methods_state") == "complete"
        and payload.get("adaptive_tle_position_v2_state") == "complete"
        and ScannerTrackingStore(bulk_root, read_only=True).analysis_status(lease.session_id).state
        == "complete"
        and _position_methods_complete(
            bulk_root,
            lease.session_id,
            expected_input_manifest_sha256=lease.input_manifest_digest,
        )
    ):
        if lease.job_kind == "adaptive_scan":
            _enqueue_tracking_after_analysis(
                bulk_root=bulk_root,
                session_id=lease.session_id,
                site=site,
                catalog=catalog,
            )
        catalog.complete_job(
            job_id=lease.job_id,
            worker_id=worker_id,
            outcome="complete",
        )
    else:
        catalog.yield_adaptive_analysis_job(job_id=lease.job_id, worker_id=worker_id)
    return True


def run_worker(
    *, bulk_root: Path, worker_id: str, poll_seconds: float, site: str = _TRACKING_SITE
) -> None:
    """Run without allocating a new database pool for every idle poll."""
    catalog, engine = _worker_catalog()
    # Restarted services must never impersonate an earlier attempt's owner.
    worker_id = f"{worker_id}-{uuid.uuid4().hex[:12]}"
    previous_sigterm = signal.signal(signal.SIGTERM, _interrupt_worker)
    next_reclaim = 0.0
    try:
        while True:
            if time.monotonic() >= next_reclaim:
                reclaimed = catalog.reclaim_expired_jobs(
                    adaptive_only=True,
                    as_of=datetime.now(UTC) - timedelta(seconds=60),
                )
                if reclaimed:
                    print(json.dumps({"reclaimed_jobs": reclaimed}), flush=True)
                next_reclaim = time.monotonic() + 60
            try:
                claimed = run_once(
                    bulk_root=bulk_root, worker_id=worker_id, catalog=catalog, site=site
                )
            except LeaseLostError as error:
                print(json.dumps({"worker_id": worker_id, "lease_lost": str(error)}), flush=True)
                claimed = False
            if not claimed:
                time.sleep(poll_seconds)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        engine.dispose()


def _interrupt_worker(_signal_number: int, _frame: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument("--site", default=os.environ.get("LEO_TRACKING_SITE", _TRACKING_SITE))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("enqueue")
    backfill = commands.add_parser("backfill-tracking")
    backfill.add_argument("--limit", type=int, default=100)
    backfill.add_argument("--since-utc-ns", type=int)
    backfill.add_argument("--until-utc-ns", type=int)
    worker = commands.add_parser("worker")
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.command == "enqueue":
        queued = enqueue_pending(bulk_root=args.bulk_root, site=args.site)
        print(json.dumps({"queued_session_ids": queued}))
        return
    if args.command == "backfill-tracking":
        queued = enqueue_tracking_backfill(
            bulk_root=args.bulk_root,
            site=args.site,
            limit=args.limit,
            since_utc_ns=args.since_utc_ns,
            until_utc_ns=args.until_utc_ns,
        )
        print(json.dumps({"queued_session_ids": queued}))
        return
    if args.once:
        run_once(bulk_root=args.bulk_root, worker_id=args.worker_id, site=args.site)
        return
    run_worker(
        bulk_root=args.bulk_root,
        worker_id=args.worker_id,
        poll_seconds=args.poll_seconds,
        site=args.site,
    )


if __name__ == "__main__":
    main()
