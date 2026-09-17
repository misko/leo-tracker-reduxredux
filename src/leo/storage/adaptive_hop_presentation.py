"""Read-only adaptive analysis metadata/PNG adapter; never starts or runs analysis."""

from pathlib import Path
from typing import Literal, cast

from leo.scanner.adaptive_dual_rx_phase_product import AdaptiveDualRxPhaseStatusV1
from leo.scanner.adaptive_hop_presentation import (
    AdaptiveHopAnalysisStatusV1,
    AdaptiveOverviewArtifact,
)
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.scanner.host_adaptive_presentation import (
    HostAdaptiveAnalysisStatusV2,
    HostAdaptiveAnalysisStatusV3,
)
from leo.scanner.host_adaptive_products import (
    HostAdaptiveAnalysisBindingV2,
    HostAdaptiveAnalysisBindingV3,
    bind_actual_visit_analysis,
)
from leo.storage.adaptive_dual_rx_phase import AdaptiveDualRxPhaseStore
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
                    HostAdaptiveAnalysisStatusV3
                    if isinstance(binding, HostAdaptiveAnalysisBindingV3)
                    else HostAdaptiveAnalysisStatusV2
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

    def phase_status(
        self, session_id: str, *, probe_stride_ms: int = 120
    ) -> AdaptiveDualRxPhaseStatusV1 | None:
        """Return only sealed metadata; never read IQ or decode GLRT visits."""
        binding = self._binding(session_id, probe_stride_ms)
        if binding is None:
            return None
        receiver_ids = cast(tuple[Literal[0, 1], ...], tuple(binding.configuration.receiver_ids))
        if receiver_ids != (0, 1):
            return AdaptiveDualRxPhaseStatusV1(
                session_id=session_id,
                input_manifest_sha256=binding.input_manifest_sha256,
                receiver_ids=receiver_ids,
                state="not_applicable",
                reason="requires_simultaneous_rx0_rx1",
                manifest=None,
            )
        store = AdaptiveDualRxPhaseStore(self._root, read_only=True)
        try:
            manifest = store.manifest(session_id, binding.input_manifest_sha256)
        finally:
            store.close()
        if manifest is None:
            return AdaptiveDualRxPhaseStatusV1(
                session_id=session_id,
                input_manifest_sha256=binding.input_manifest_sha256,
                receiver_ids=receiver_ids,
                state="pending",
                reason="awaiting_phase_analysis",
                manifest=None,
            )
        if manifest.glrt_binding_sha256 != binding.sha256:
            raise ValueError("adaptive phase result changed the GLRT binding")
        return AdaptiveDualRxPhaseStatusV1(
            session_id=session_id,
            input_manifest_sha256=binding.input_manifest_sha256,
            receiver_ids=receiver_ids,
            state=manifest.state,
            reason=manifest.reason,
            manifest=manifest,
        )

    def phase_artifact(
        self,
        session_id: str,
        *,
        glrt_binding_sha256: str,
        artifact_sha256: str,
        probe_stride_ms: int = 120,
    ) -> bytes | None:
        status = self.phase_status(session_id, probe_stride_ms=probe_stride_ms)
        if status is None or status.manifest is None:
            return None
        if status.manifest.glrt_binding_sha256 != glrt_binding_sha256:
            raise ValueError("adaptive phase artifact changed the GLRT binding")
        store = AdaptiveDualRxPhaseStore(self._root, read_only=True)
        try:
            return store.artifact(status.manifest, expected_sha256=artifact_sha256)
        finally:
            store.close()
