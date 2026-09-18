from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from types import SimpleNamespace

from leo.catalog.types import AdaptiveAnalysisJobLease
from leo.cli import adaptive_processing_queue as subject


def _lease() -> AdaptiveAnalysisJobLease:
    return AdaptiveAnalysisJobLease(
        job_id=7,
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
        def claim_adaptive_analysis_job(self, **kwargs):
            return _lease()

        def complete_job(self, **kwargs):
            calls.append(("complete", kwargs))

    monkeypatch.setattr(subject, "_catalog", Catalog)
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
    assert calls == [("complete", {"job_id": 7, "worker_id": "worker-1", "outcome": "complete"})]


def test_run_once_yields_checkpointed_slice(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []

    class Catalog:
        def claim_adaptive_analysis_job(self, **kwargs):
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
