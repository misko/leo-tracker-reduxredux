from __future__ import annotations

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
