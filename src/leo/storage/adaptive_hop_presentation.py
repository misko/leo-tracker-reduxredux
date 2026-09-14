"""Read-only adaptive analysis metadata/PNG adapter; never starts or runs analysis."""

from pathlib import Path

from leo.scanner.adaptive_hop_presentation import (
    AdaptiveHopAnalysisStatusV1,
    AdaptiveOverviewArtifact,
)
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.scanner.host_adaptive_presentation import HostAdaptiveAnalysisStatusV2
from leo.scanner.host_adaptive_products import (
    HostAdaptiveAnalysisBindingV2,
    bind_actual_visit_analysis,
)
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.errors import BundleNotFoundError


class AdaptiveHopAnalysisPresentationStore:
    def __init__(self, root: Path):
        self._root = root

    def _binding(
        self, session_id: str, probe_stride_ms: int
    ) -> AdaptiveHopAnalysisBindingV1 | None:
        store = AdaptiveHopIqStore(self._root, read_only=True)
        try:
            try:
                capture = store.inspect(session_id)
            except BundleNotFoundError:
                return None
            return bind_actual_visit_analysis(
                capture.manifest.receipt,
                input_manifest_sha256=capture.manifest_sha256,
                probe_stride_ms=probe_stride_ms,
            )
        finally:
            store.close()

    def status(
        self, session_id: str, *, probe_stride_ms: int = 10
    ) -> AdaptiveHopAnalysisStatusV1 | None:
        binding = self._binding(session_id, probe_stride_ms)
        if binding is None:
            return None
        store = AdaptiveHopAnalysisStore(self._root, read_only=True)
        try:
            try:
                with store.job(binding) as job:
                    return job.status()
            except BundleNotFoundError:
                status_model: type[AdaptiveHopAnalysisStatusV1] = (
                    HostAdaptiveAnalysisStatusV2
                    if isinstance(binding, HostAdaptiveAnalysisBindingV2)
                    else AdaptiveHopAnalysisStatusV1
                )
                return status_model(
                    session_id=session_id,
                    input_manifest_sha256=binding.input_manifest_sha256,
                    binding_sha256=binding.sha256,
                    configuration=binding.configuration,
                    total_visits=binding.receipt.complete_visit_count,
                    checkpoint_visits=0,
                    state="not_started",
                    progress_basis="no_checkpoints",
                    metrics_manifest_sha256=None,
                    overview=None,
                )
        finally:
            store.close()

    def artifact(
        self,
        session_id: str,
        artifact: AdaptiveOverviewArtifact,
        *,
        binding_sha256: str,
        artifact_sha256: str,
        probe_stride_ms: int = 10,
    ) -> bytes | None:
        binding = self._binding(session_id, probe_stride_ms)
        if binding is None:
            return None
        if binding.sha256 != binding_sha256:
            raise ValueError("adaptive artifact request changes source/configuration binding")
        store = AdaptiveHopAnalysisStore(self._root, read_only=True)
        try:
            try:
                with store.job(binding) as job:
                    return job.read_artifact(artifact, expected_sha256=artifact_sha256)
            except BundleNotFoundError:
                return None
        finally:
            store.close()
