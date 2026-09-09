"""Bounded, resumable actual-visit analysis through public component ports."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol

from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopAnalysisSource,
    AdaptiveHopVisitAnalysisV1,
    analyze_adaptive_hop_visit,
)
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
    AdaptiveHopVisitReferenceV1,
)


class AdaptiveHopAnalysisInputs(Protocol):
    def source(self, session_id: str) -> AbstractContextManager[AdaptiveHopAnalysisSource]: ...


class AdaptiveHopAnalysisJob(Protocol):
    def verify(self) -> AdaptiveHopMetricsManifestV1 | None: ...
    def completed_visits(self) -> tuple[int, ...]: ...
    def write_visit(self, product: AdaptiveHopVisitAnalysisV1) -> AdaptiveHopVisitReferenceV1: ...
    def finalize_metrics(self) -> AdaptiveHopMetricsManifestV1: ...


class AdaptiveHopAnalysisProducts(Protocol):
    def job(
        self, binding: AdaptiveHopAnalysisBindingV1, *, writable: bool = False
    ) -> AbstractContextManager[AdaptiveHopAnalysisJob]: ...


@dataclass(frozen=True, slots=True)
class AdaptiveHopAnalysisRun:
    session_id: str
    binding_sha256: str
    state: Literal["partial", "metrics_complete"]
    total_visits: int
    completed_visits: int
    newly_analyzed_visits: int
    stop_reason: Literal["complete", "visit_budget", "time_budget", "cancelled"]


class AdaptiveHopAnalysisService:
    def __init__(
        self,
        *,
        inputs: AdaptiveHopAnalysisInputs,
        products: AdaptiveHopAnalysisProducts,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._inputs, self._products, self._clock = inputs, products, clock

    def analyze_session(
        self,
        session_id: str,
        *,
        maximum_visits: int = 2500,
        maximum_seconds: float = 300,
        probe_stride_ms: int = 10,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> AdaptiveHopAnalysisRun:
        """Budget/cancel at visit boundaries; never truncate scientific windows.

        A running visit may exceed the time budget. Completed checkpoints survive
        errors; neither a partial result nor metrics completion asserts UI readiness.
        """
        if type(maximum_visits) is not int or not 1 <= maximum_visits <= 2500:
            raise ValueError("adaptive analysis visit budget must be in 1..2500")
        if (
            isinstance(maximum_seconds, bool)
            or not math.isfinite(maximum_seconds)
            or not (0 < maximum_seconds <= 1800)
        ):
            raise ValueError("adaptive analysis time budget must be in (0, 1800] seconds")
        # Validate geometry/options before opening source or output directories.
        AdaptiveHopAnalysisConfigurationV1(
            sample_rate_hz=2_500_000, probe_stride_ms=probe_stride_ms
        )
        started = self._clock()
        with self._inputs.source(session_id) as source:
            if source.receipt.session_id != session_id:
                raise ValueError("adaptive analysis input changed requested identity")
            configuration = AdaptiveHopAnalysisConfigurationV1(
                sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                probe_stride_ms=probe_stride_ms,
            )
            binding = AdaptiveHopAnalysisBindingV1(
                receipt=source.receipt,
                input_manifest_sha256=source.input_manifest_sha256,
                configuration=configuration,
            )
            total, count = len(source.visits), 0
            with self._products.job(binding, writable=True) as job:
                manifest = job.verify()
                completed = set(job.completed_visits())
                reason: Literal["complete", "visit_budget", "time_budget", "cancelled"] = "complete"
                if manifest is None:
                    for index in range(total):
                        if index in completed:
                            continue
                        if cancelled():
                            reason = "cancelled"
                            break
                        if count >= maximum_visits:
                            reason = "visit_budget"
                            break
                        if self._clock() - started >= maximum_seconds:
                            reason = "time_budget"
                            break
                        product = analyze_adaptive_hop_visit(
                            source, index, configuration=configuration
                        )
                        job.write_visit(product)
                        completed.add(index)
                        count += 1
                    if len(completed) == total:
                        manifest = job.finalize_metrics()
                return AdaptiveHopAnalysisRun(
                    session_id=session_id,
                    binding_sha256=binding.sha256,
                    state="metrics_complete" if manifest is not None else "partial",
                    total_visits=total,
                    completed_visits=len(completed),
                    newly_analyzed_visits=count,
                    stop_reason=reason,
                )
