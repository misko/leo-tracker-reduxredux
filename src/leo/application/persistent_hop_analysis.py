"""Restartable orchestration for long persistent-hop scanner analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from leo.scanner.persistent_hop import PersistentHopSessionReceiptV1
from leo.scanner.persistent_hop_analysis import (
    PersistentHopAnalysisSource,
    PersistentHopGlrt64Configuration,
)
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV1,
    PersistentHopAnalysisConfigurationV1,
    PersistentHopAnalysisManifestV1,
    PersistentHopAnalysisStatusV1,
)
from leo.scanner.persistent_hop_standard_analysis import (
    analyze_persistent_hop_sweep,
    persistent_hop_product_configuration,
)


class PersistentHopAnalysisInputs(Protocol):
    def session_ids(self) -> tuple[str, ...]: ...

    def source(self, session_id: str) -> PersistentHopAnalysisSource: ...


class _PublishedPersistentHopAnalysis(Protocol):
    @property
    def manifest(self) -> PersistentHopAnalysisManifestV1: ...


class PersistentHopAnalysisProducts(Protocol):
    def begin_or_resume(
        self,
        *,
        session_id: str,
        input_manifest_sha256: str,
        configuration: PersistentHopAnalysisConfigurationV1,
    ) -> datetime: ...

    def completed_sweeps(self, session_id: str) -> tuple[int, ...]: ...

    def write_chunk(
        self,
        session_id: str,
        chunk: PersistentHopAnalysisChunkV1,
    ) -> object: ...

    def work_chunks(self, session_id: str) -> tuple[PersistentHopAnalysisChunkV1, ...]: ...

    def publish(
        self,
        *,
        session_id: str,
        input_uri: str,
        sample_rate_hz: int,
        bandwidth_hz: int,
        visit_count: int,
        artifacts: dict[str, bytes],
    ) -> _PublishedPersistentHopAnalysis: ...

    def inspect(self, session_id: str) -> _PublishedPersistentHopAnalysis: ...

    def is_complete(self, session_id: str) -> bool: ...

    def write_status(self, status: PersistentHopAnalysisStatusV1) -> None: ...


PersistentHopRenderer = Callable[
    [PersistentHopSessionReceiptV1, tuple[PersistentHopAnalysisChunkV1, ...]],
    dict[str, bytes],
]


@dataclass(frozen=True, slots=True)
class PersistentHopAnalysisRunSummary:
    requested_session_count: int
    completed_session_ids: tuple[str, ...]
    skipped_session_ids: tuple[str, ...]
    failures: tuple[str, ...]


class PersistentHopAnalysisService:
    """Analyze selected sessions sequentially, checkpointing after every sweep."""

    def __init__(
        self,
        *,
        inputs: PersistentHopAnalysisInputs,
        products: PersistentHopAnalysisProducts,
        renderer: PersistentHopRenderer,
        probe_stride_ms: int = 10,
        maximum_workers: int = 1,
    ) -> None:
        self._inputs = inputs
        self._products = products
        self._renderer = renderer
        self._probe_stride_ms = probe_stride_ms
        self._maximum_workers = maximum_workers

    def analyze_session(self, session_id: str) -> PersistentHopAnalysisManifestV1:
        if self._products.is_complete(session_id):
            return self._products.inspect(session_id).manifest
        source = self._inputs.source(session_id)
        total_visits = len(source.visits)
        configuration = PersistentHopGlrt64Configuration(
            source.plan,
            probe_stride_ms=self._probe_stride_ms,
        )
        persisted_configuration = persistent_hop_product_configuration(configuration)
        self._products.begin_or_resume(
            session_id=session_id,
            input_manifest_sha256=source.input_manifest_sha256,
            configuration=persisted_configuration,
        )
        completed_sweeps = set(self._products.completed_sweeps(session_id))
        analyzed_visits = sum(span.sweep_index in completed_sweeps for span in source.visits)
        self._products.write_status(
            PersistentHopAnalysisStatusV1(
                session_id=session_id,
                state="running",
                total_visits=total_visits,
                analyzed_visits=analyzed_visits,
                updated_at=datetime.now(tz=UTC),
            )
        )
        sweep_indexes = tuple(dict.fromkeys(span.sweep_index for span in source.visits))
        try:
            for sweep_index in sweep_indexes:
                if sweep_index in completed_sweeps:
                    continue
                chunk = analyze_persistent_hop_sweep(
                    source,
                    sweep_index,
                    configuration=configuration,
                    maximum_workers=self._maximum_workers,
                )
                self._products.write_chunk(session_id, chunk)
                analyzed_visits += chunk.visit_count
                self._products.write_status(
                    PersistentHopAnalysisStatusV1(
                        session_id=session_id,
                        state="running",
                        total_visits=total_visits,
                        analyzed_visits=analyzed_visits,
                        updated_at=datetime.now(tz=UTC),
                    )
                )
            chunks = self._products.work_chunks(session_id)
            artifacts = self._renderer(source.receipt, chunks)
            return self._products.publish(
                session_id=session_id,
                input_uri=source.input_uri,
                sample_rate_hz=source.sample_rate_hz,
                bandwidth_hz=source.bandwidth_hz,
                visit_count=total_visits,
                artifacts=artifacts,
            ).manifest
        except Exception as error:
            summary = f"{type(error).__name__}: {error}"[:512]
            self._products.write_status(
                PersistentHopAnalysisStatusV1(
                    session_id=session_id,
                    state="failed",
                    total_visits=total_visits,
                    analyzed_visits=analyzed_visits,
                    updated_at=datetime.now(tz=UTC),
                    failure_summary=summary,
                )
            )
            raise

    def run_pending(
        self,
        *,
        maximum_sessions: int = 1,
        session_id: str | None = None,
    ) -> PersistentHopAnalysisRunSummary:
        if not 1 <= maximum_sessions <= 100:
            raise ValueError("persistent-hop analysis session bound must lie in 1..100")
        candidates = (session_id,) if session_id is not None else self._inputs.session_ids()
        selected = tuple(item for item in candidates if not self._products.is_complete(item))[
            :maximum_sessions
        ]
        completed: list[str] = []
        failures: list[str] = []
        for candidate in selected:
            try:
                self.analyze_session(candidate)
            except Exception as error:
                failures.append(f"{candidate}: {type(error).__name__}: {error}")
            else:
                completed.append(candidate)
        skipped = tuple(item for item in candidates if item not in selected)
        return PersistentHopAnalysisRunSummary(
            requested_session_count=len(selected),
            completed_session_ids=tuple(completed),
            skipped_session_ids=skipped,
            failures=tuple(failures),
        )
