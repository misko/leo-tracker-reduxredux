"""Render finalized metrics through narrow ports without repeating IQ analysis."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Protocol

from leo.application.adaptive_hop_analysis import AdaptiveHopAnalysisInputs
from leo.scanner.adaptive_hop_analysis import (
    AdaptiveHopAnalysisConfigurationV1,
    AdaptiveHopVisitAnalysisV1,
)
from leo.scanner.adaptive_hop_presentation import (
    AdaptiveHopOverviewManifestV1,
    RenderedAdaptiveOverview,
)
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    AdaptiveHopMetricsManifestV1,
)


class AdaptiveOverviewJob(Protocol):
    def manifest(self) -> AdaptiveHopMetricsManifestV1 | None: ...
    def overview(self) -> AdaptiveHopOverviewManifestV1 | None: ...
    def published_visits(self) -> Iterator[AdaptiveHopVisitAnalysisV1]: ...
    def read_artifact(self, name: str, *, expected_sha256: str) -> bytes | None: ...
    def publish_overview(
        self, rendered: RenderedAdaptiveOverview
    ) -> AdaptiveHopOverviewManifestV1: ...


class AdaptiveOverviewProducts(Protocol):
    def job(
        self, binding: AdaptiveHopAnalysisBindingV1, *, writable: bool = False
    ) -> AbstractContextManager[AdaptiveOverviewJob]: ...


class AdaptiveHopOverviewService:
    def __init__(
        self,
        *,
        inputs: AdaptiveHopAnalysisInputs,
        products: AdaptiveOverviewProducts,
        renderer: Callable[
            [
                AdaptiveHopAnalysisBindingV1,
                AdaptiveHopMetricsManifestV1,
                Iterator[AdaptiveHopVisitAnalysisV1],
            ],
            RenderedAdaptiveOverview,
        ],
    ):
        self._inputs, self._products, self._renderer = inputs, products, renderer

    def render_session(
        self, session_id: str, *, probe_stride_ms: int = 10
    ) -> AdaptiveHopOverviewManifestV1:
        with self._inputs.source(session_id) as source:
            if source.receipt.session_id != session_id:
                raise ValueError("adaptive overview source identity differs")
            binding = AdaptiveHopAnalysisBindingV1(
                receipt=source.receipt,
                input_manifest_sha256=source.input_manifest_sha256,
                configuration=AdaptiveHopAnalysisConfigurationV1(
                    sample_rate_hz=source.receipt.plan.geometry.sample_rate_hz,
                    probe_stride_ms=probe_stride_ms,
                ),
            )
            with self._products.job(binding, writable=True) as job:
                metrics = job.manifest()
                if metrics is None:
                    raise ValueError("adaptive overview requires finalized metrics")
                existing = job.overview()
                if existing is not None:
                    for artifact in existing.artifacts:
                        if (
                            job.read_artifact(artifact.name, expected_sha256=artifact.sha256)
                            is None
                        ):
                            raise ValueError("adaptive overview lost a published artifact")
                    return existing
                return job.publish_overview(
                    self._renderer(binding, metrics, job.published_visits())
                )
