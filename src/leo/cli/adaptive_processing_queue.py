"""Schedule and execute adaptive scanner analysis in the shared processing queue."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

from sqlalchemy import Engine

from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore

_LEASE = timedelta(minutes=20)
_SLICE_SECONDS = 560


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
    engine = create_catalog_engine(database_url, pool_size=1, max_overflow=0)
    return CatalogRepository(create_session_factory(engine)), engine


def enqueue_pending(*, bulk_root: Path) -> tuple[str, ...]:
    captures = AdaptiveHopIqStore(bulk_root, read_only=True)
    presentation = AdaptiveHopAnalysisPresentationStore(bulk_root)
    catalog = _catalog()
    queued: list[str] = []
    try:
        for _, session_id in captures.publication_index():
            capture = captures.inspect(session_id)
            status = presentation.status_for_capture(capture, probe_stride_ms=120)
            if status.state == "figures_ready":
                continue
            recent_cutoff = time.time_ns() - 2 * 3600 * 10**9
            priority = 100 if capture.manifest.created_utc_ns > recent_cutoff else 0
            if catalog.enqueue_adaptive_analysis_job(
                session_id=session_id,
                input_manifest_digest=capture.manifest_sha256,
                configuration_digest=status.binding_sha256,
                priority=priority,
            ):
                queued.append(session_id)
    finally:
        captures.close()
    return tuple(queued)


def run_once(*, bulk_root: Path, worker_id: str, catalog: CatalogRepository | None = None) -> bool:
    catalog = _catalog() if catalog is None else catalog
    lease = catalog.claim_adaptive_analysis_job(worker_id=worker_id, lease_for=_LEASE)
    if lease is None:
        return False
    command = [
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
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    payload = json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else {}
    if completed.returncode or payload.get("state") == "failed":
        catalog.fail_job(
            job_id=lease.job_id,
            worker_id=worker_id,
            error=(completed.stderr or completed.stdout)[-1024:],
            retryable=True,
            retry_after=timedelta(minutes=2),
        )
    elif payload.get("state") == "metrics_complete" and payload.get("overview_state") == "ready":
        catalog.complete_job(job_id=lease.job_id, worker_id=worker_id, outcome="complete")
    else:
        catalog.yield_adaptive_analysis_job(job_id=lease.job_id, worker_id=worker_id)
    return True


def run_worker(*, bulk_root: Path, worker_id: str, poll_seconds: float) -> None:
    """Run without allocating a new database pool for every idle poll."""
    catalog, engine = _worker_catalog()
    try:
        while True:
            claimed = run_once(bulk_root=bulk_root, worker_id=worker_id, catalog=catalog)
            if not claimed:
                time.sleep(poll_seconds)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("enqueue")
    worker = commands.add_parser("worker")
    worker.add_argument("--worker-id", required=True)
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.command == "enqueue":
        print(json.dumps({"queued_session_ids": enqueue_pending(bulk_root=args.bulk_root)}))
        return
    if args.once:
        run_once(bulk_root=args.bulk_root, worker_id=args.worker_id)
        return
    run_worker(
        bulk_root=args.bulk_root,
        worker_id=args.worker_id,
        poll_seconds=args.poll_seconds,
    )


if __name__ == "__main__":
    main()
