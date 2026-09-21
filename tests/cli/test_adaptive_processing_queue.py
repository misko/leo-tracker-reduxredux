from __future__ import annotations

from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from leo.catalog.types import AdaptiveAnalysisJobLease
from leo.cli import adaptive_processing_queue as subject


def test_tracking_queue_identity_invalidates_legacy_control_gates(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        subject, "canonical_digest", lambda value: payloads.append(value) or "digest"
    )
    monkeypatch.setattr(
        subject,
        "resolve_preset",
        lambda site: SimpleNamespace(model_dump=lambda **kwargs: {"site": site}),
    )
    subject._tracking_digest(
        capture=SimpleNamespace(manifest_sha256="capture"),
        metrics_manifest_sha256="metrics",
        site="test",
    )
    assert payloads[0]["association_gates"] == "nominal-catalogue-only-v1"


def test_completed_old_analysis_enqueues_tracking_without_live_window_cutoff(
    monkeypatch, tmp_path
) -> None:
    capture = SimpleNamespace(
        manifest_sha256="sha256:" + "1" * 64,
        manifest=SimpleNamespace(created_utc_ns=1),
    )
    status = SimpleNamespace(
        state="figures_ready",
        metrics_manifest_sha256="sha256:" + "2" * 64,
    )
    calls: list[dict[str, object]] = []

    class Captures:
        def __init__(self, *_args, **_kwargs):
            pass

        def inspect(self, session_id):
            assert session_id == "scan-fw-0123456789abcdef"
            return capture

        def close(self):
            pass

    class Presentation:
        def __init__(self, *_args, **_kwargs):
            pass

        def status_for_capture(self, actual, *, probe_stride_ms):
            assert actual is capture
            assert probe_stride_ms == 120
            return status

    class Tracking:
        def __init__(self, *_args, **_kwargs):
            pass

        def analysis_status(self, session_id):
            assert session_id == "scan-fw-0123456789abcdef"
            return SimpleNamespace(state="pending")

    class Catalog:
        def enqueue_adaptive_tracking_job(self, **kwargs):
            calls.append(kwargs)
            return True

    monkeypatch.setattr(subject, "AdaptiveHopIqStore", Captures)
    monkeypatch.setattr(subject, "AdaptiveHopAnalysisPresentationStore", Presentation)
    monkeypatch.setattr(subject, "ScannerTrackingStore", Tracking)
    monkeypatch.setattr(subject, "_tracking_digest", lambda **_kwargs: "tracking-digest")

    assert subject._enqueue_tracking_after_analysis(
        bulk_root=tmp_path,
        session_id="scan-fw-0123456789abcdef",
        site="test-site",
        catalog=Catalog(),
    )
    assert calls == [
        {
            "session_id": "scan-fw-0123456789abcdef",
            "input_manifest_digest": capture.manifest_sha256,
            "configuration_digest": "tracking-digest",
            "priority": 0,
        }
    ]


def _lease() -> AdaptiveAnalysisJobLease:
    return AdaptiveAnalysisJobLease(
        job_id=7,
        job_kind="adaptive_scan",
        session_id="scan-fw-0123456789abcdef",
        input_manifest_digest="sha256:" + "1" * 64,
        configuration_digest="sha256:" + "2" * 64,
        attempt_number=1,
        worker_id="worker-1",
        lease_expires_at=datetime.now(UTC),
        resource_class="memory",
    )


def test_run_once_completes_figures_ready_slice(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, object]] = []

    class Catalog:
        def claim_adaptive_job(self, **kwargs):
            return _lease()

        def complete_job(self, **kwargs):
            calls.append(("complete", kwargs))

    monkeypatch.setattr(subject, "_catalog", Catalog)
    monkeypatch.setattr(
        subject,
        "_enqueue_tracking_after_analysis",
        lambda **kwargs: calls.append(("enqueue-tracking", kwargs)) or True,
    )
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout='{"state":"metrics_complete","overview_state":"ready"}',
            stderr="",
        ),
    )

    assert subject.run_once(bulk_root=tmp_path, worker_id="worker-1")
    assert calls[0][0] == "enqueue-tracking"
    enqueue = calls[0][1]
    assert isinstance(enqueue, dict)
    assert enqueue["bulk_root"] == tmp_path
    assert enqueue["session_id"] == "scan-fw-0123456789abcdef"
    assert enqueue["site"] == "spinnaker-sausalito"
    assert isinstance(enqueue["catalog"], Catalog)
    assert calls[1] == (
        "complete",
        {"job_id": 7, "worker_id": "worker-1", "outcome": "complete"},
    )


def test_run_once_yields_checkpointed_slice(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    class Catalog:
        def claim_adaptive_job(self, **kwargs):
            return _lease()

        def yield_adaptive_analysis_job(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(subject, "_catalog", Catalog)
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout='{"state":"partial"}', stderr=""
        ),
    )

    assert subject.run_once(bulk_root=tmp_path, worker_id="worker-1")
    assert calls == [{"job_id": 7, "worker_id": "worker-1"}]


def test_run_once_completes_tracking_publication(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    class Catalog:
        def claim_adaptive_job(self, **kwargs):
            return replace(_lease(), job_kind="adaptive_tracking", resource_class="heavy")

        def complete_job(self, **kwargs):
            calls.append(kwargs)

    command: list[str] = []
    monkeypatch.setattr(subject, "_catalog", Catalog)
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda args, **kwargs: (
            command.extend(args)
            or SimpleNamespace(returncode=0, stdout='{"state":"complete"}', stderr="")
        ),
    )

    assert subject.run_once(bulk_root=tmp_path, worker_id="worker-1")
    assert "leo.cli.scanner_tracking" in command
    assert "--queue-worker" in command
    assert command[command.index("--review-limit") + 1] == "64"
    assert calls == [{"job_id": 7, "worker_id": "worker-1", "outcome": "complete"}]


def test_run_once_yields_its_lease_when_stopped(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    class Catalog:
        def claim_adaptive_job(self, **kwargs):
            return _lease()

        def yield_adaptive_analysis_job(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(subject, "_catalog", Catalog)
    monkeypatch.setattr(
        subject.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with suppress(KeyboardInterrupt):
        subject.run_once(bulk_root=tmp_path, worker_id="worker-1")

    assert calls == [{"job_id": 7, "worker_id": "worker-1"}]


def test_worker_reuses_one_bounded_catalog_pool_and_disposes_it(monkeypatch, tmp_path) -> None:
    class Catalog:
        pass

    class Engine:
        disposed = False

        def dispose(self) -> None:
            self.disposed = True

    catalog = Catalog()
    engine = Engine()
    seen_catalogs: list[object] = []

    monkeypatch.setattr(subject, "_worker_catalog", lambda: (catalog, engine))

    def run_once(**kwargs) -> bool:
        seen_catalogs.append(kwargs["catalog"])
        return False

    monkeypatch.setattr(subject, "run_once", run_once)

    def stop_after_first_poll(_seconds: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(subject.time, "sleep", stop_after_first_poll)

    with suppress(KeyboardInterrupt):
        subject.run_worker(bulk_root=tmp_path, worker_id="worker-1", poll_seconds=2.0)

    assert seen_catalogs == [catalog]
    assert engine.disposed


def test_worker_catalog_limits_its_database_pool_to_one_connection(monkeypatch) -> None:
    engine = object()
    factory = object()
    catalog = object()
    calls: list[tuple[object, dict[str, object]]] = []

    def create_engine(database_url: str, **kwargs: object) -> object:
        calls.append((database_url, kwargs))
        return engine

    monkeypatch.setenv("LEO_DATABASE_URL", "postgresql+psycopg://catalog")
    monkeypatch.setattr(subject, "create_catalog_engine", create_engine)
    monkeypatch.setattr(subject, "create_session_factory", lambda actual: factory)
    monkeypatch.setattr(subject, "CatalogRepository", lambda actual: catalog)

    assert subject._worker_catalog() == (catalog, engine)
    assert calls == [
        (
            "postgresql+psycopg://catalog",
            {"pool_size": 1, "max_overflow": 0},
        )
    ]
