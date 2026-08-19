from __future__ import annotations

import logging
import resource
import tracemalloc
from threading import Event
from types import SimpleNamespace
from typing import cast

from leo.cli import processing as processing_module
from leo.cli.processing import LocalProcessingBackend, ProcessingServices
from leo.pipeline import StageOutcome
from leo.processing import RunRejectedError, WorkerExecution


class _ManyJobProcessing:
    def __init__(self, *, reject_every: int | None = None) -> None:
        self.count = 0
        self.reject_every = reject_every

    def run_once(self, *, worker_id: str) -> WorkerExecution:
        del worker_id
        self.count += 1
        return WorkerExecution(
            job_id=self.count,
            run_id=f"run-{self.count}",
            stage_key="quality",
            scope_key="stream-0",
            succeeded=True,
            outcome=StageOutcome.COMPLETE,
            error=None,
        )

    def finalize_run(self, run_id: str) -> None:
        index = int(run_id.removeprefix("run-"))
        if self.reject_every is not None and index % self.reject_every == 0:
            raise RunRejectedError("injected terminal rejection")


class _NoReadyRunsCatalog:
    def ready_run_ids(self) -> tuple[str, ...]:
        return ()


def _backend(processing: _ManyJobProcessing) -> LocalProcessingBackend:
    services = SimpleNamespace(
        processing=processing,
        catalog=_NoReadyRunsCatalog(),
    )
    return LocalProcessingBackend(cast(ProcessingServices, services))


def test_long_running_worker_evidence_and_memory_are_bounded(
    monkeypatch,
) -> None:
    job_count = 10_000
    monkeypatch.setattr(processing_module.logger, "disabled", True)
    before_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    tracemalloc.start()

    result = _backend(_ManyJobProcessing(reject_every=5)).worker(
        worker_id="memory-worker",
        poll_seconds=0.01,
        maximum_jobs=job_count,
        once=False,
        cancel=Event(),
    )

    _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    after_rss_kib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    assert result.claimed_count == job_count
    assert result.finalized_count == 8_000
    assert result.rejected_count == 2_000
    assert result.error_count == 2_000
    assert len(result.executions) == result.evidence_limit == 256
    assert len(result.finalized_run_ids) == 256
    assert len(result.rejected_run_ids) == 256
    assert len(result.errors) == 256
    assert result.execution_evidence_omitted_count == 9_744
    assert result.finalized_id_evidence_omitted_count == 7_744
    assert result.rejected_id_evidence_omitted_count == 1_744
    assert result.error_evidence_omitted_count == 1_744
    assert peak_bytes < 8 * 1024 * 1024
    assert after_rss_kib - before_rss_kib < 32 * 1024


def test_worker_emits_per_job_and_finalization_logs(caplog) -> None:
    processing_module.logger.disabled = False
    with caplog.at_level(logging.INFO, logger=processing_module.__name__):
        result = _backend(_ManyJobProcessing()).worker(
            worker_id="logging-worker",
            poll_seconds=0.01,
            maximum_jobs=1,
            once=False,
            cancel=Event(),
        )

    assert result.claimed_count == 1
    assert "worker job job_id=1 run_id=run-1" in caplog.text
    assert "worker finalized run_id=run-1" in caplog.text
