"""Read-only adaptive analysis metadata/PNG adapter; never starts or runs analysis."""

from pathlib import Path
from typing import Literal, cast

from leo.scanner.adaptive_dual_rx_phase_product import AdaptiveDualRxPhaseStatusV1
from leo.scanner.adaptive_dual_rx_phase_product_v2 import AdaptiveDualRxPhaseStatusV2
from leo.scanner.adaptive_hop_presentation import (
    AdaptiveHopAnalysisStatusV1,
    AdaptiveOverviewArtifact,
    DualRx10mAdaptiveAnalysisStatusV5,
    EdgeAdaptiveAnalysisStatusV4,
    Feature103AnalysisStatusV6,
    Feature104AnalysisStatusV7,
)
from leo.scanner.adaptive_hop_products import (
    AdaptiveHopAnalysisBindingV1,
    DualRx10mAdaptiveAnalysisBindingV5,
    EdgeAdaptiveAnalysisBindingV4,
    Feature103AnalysisBindingV6,
    Feature104AnalysisBindingV7,
)
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
from leo.storage.adaptive_dual_rx_phase_v2 import AdaptiveDualRxPhaseStoreV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.errors import BundleNotFoundError


class AdaptiveHopAnalysisPresentationStore:
    def __init__(self, root: Path):
        self._root = root

    def relative_phase_status(self, session_id: str, *, probe_stride_ms: int = 120):
        from leo.scanner.adaptive_relative_phase import (
            RelativePhaseStatusV1,
            relative_phase_binding,
        )
        from leo.storage.adaptive_relative_phase import RelativePhaseStore

        binding = self._binding(session_id, probe_stride_ms)
        if binding is None:
            return None
        digest = relative_phase_binding(binding.input_manifest_sha256, binding.sha256)
        try:
            with RelativePhaseStore(self._root, read_only=True).job(session_id, digest) as job:
                manifest = job.manifest()
        except FileNotFoundError:
            manifest = None
        if manifest is not None and (
            manifest.input_manifest_sha256 != binding.input_manifest_sha256
            or manifest.glrt_binding_sha256 != binding.sha256
        ):
            raise ValueError("Relative phase manifest changed its source binding")
        return RelativePhaseStatusV1(
            session_id=session_id,
            input_manifest_sha256=binding.input_manifest_sha256,
            binding_sha256=digest,
            state="pending" if manifest is None else manifest.state,
            manifest=manifest,
        )

    def relative_phase_artifact(
        self, session_id, name, *, binding_sha256, artifact_sha256, probe_stride_ms=120
    ):
        from leo.storage.adaptive_relative_phase import RelativePhaseStore

        status = self.relative_phase_status(session_id, probe_stride_ms=probe_stride_ms)
        if status is None or status.manifest is None:
            return None
        if status.binding_sha256 != binding_sha256:
            raise ValueError("Phase artifact source changed")
        with RelativePhaseStore(self._root, read_only=True).job(session_id, binding_sha256) as job:
            return job.artifact(name, artifact_sha256)

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
        return self._status(binding)

    def status_for_capture(
        self, capture, *, probe_stride_ms: int = 10
    ) -> AdaptiveHopAnalysisStatusV1:
        """Read status for an already validated capture without reopening its manifest."""
        binding = bind_actual_visit_analysis(
            capture.manifest.receipt,
            input_manifest_sha256=capture.manifest_sha256,
            probe_stride_ms=probe_stride_ms,
        )
        return self._status(binding)

    def _status(
        self,
        binding: AdaptiveHopAnalysisBindingV1
        | HostAdaptiveAnalysisBindingV2
        | HostAdaptiveAnalysisBindingV3,
    ) -> AdaptiveHopAnalysisStatusV1:
        store = AdaptiveHopAnalysisStore(self._root, read_only=True)
        try:
            try:
                with store.job(binding) as job:
                    return job.status()
            except BundleNotFoundError:
                status_model: type[AdaptiveHopAnalysisStatusV1] = (
                    Feature104AnalysisStatusV7
                    if isinstance(binding, Feature104AnalysisBindingV7)
                    else Feature103AnalysisStatusV6
                    if isinstance(binding, Feature103AnalysisBindingV6)
                    else DualRx10mAdaptiveAnalysisStatusV5
                    if isinstance(binding, DualRx10mAdaptiveAnalysisBindingV5)
                    else HostAdaptiveAnalysisStatusV3
                    if isinstance(binding, HostAdaptiveAnalysisBindingV3)
                    else HostAdaptiveAnalysisStatusV2
                    if isinstance(binding, HostAdaptiveAnalysisBindingV2)
                    else EdgeAdaptiveAnalysisStatusV4
                    if isinstance(binding, EdgeAdaptiveAnalysisBindingV4)
                    else AdaptiveHopAnalysisStatusV1
                )
                return status_model(
                    session_id=binding.session_id,
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

    def phase_status_v2(
        self, session_id: str, *, probe_stride_ms: int = 120
    ) -> AdaptiveDualRxPhaseStatusV2 | None:
        """Return V2 checkpoint/final metadata without reading IQ or GLRT visits."""
        binding = self._binding(session_id, probe_stride_ms)
        if binding is None:
            return None
        receiver_ids = cast(tuple[Literal[0, 1], ...], tuple(binding.configuration.receiver_ids))
        total = binding.receipt.complete_visit_count
        if receiver_ids != (0, 1):
            return AdaptiveDualRxPhaseStatusV2(
                session_id=session_id,
                input_manifest_sha256=binding.input_manifest_sha256,
                receiver_ids=receiver_ids,
                state="not_applicable",
                reason="requires_simultaneous_rx0_rx1",
                checkpoint_visit_count=0,
                total_visit_count=total,
                manifest=None,
            )
        store = AdaptiveDualRxPhaseStoreV2(self._root, read_only=True)
        try:
            completed = store.completed_visits(
                session_id, binding.input_manifest_sha256, binding.sha256
            )
            manifest = store.manifest(session_id, binding.input_manifest_sha256, binding.sha256)
        finally:
            store.close()
        if manifest is None:
            return AdaptiveDualRxPhaseStatusV2(
                session_id=session_id,
                input_manifest_sha256=binding.input_manifest_sha256,
                receiver_ids=receiver_ids,
                state="pending",
                reason="awaiting_phase_analysis",
                checkpoint_visit_count=len(completed),
                total_visit_count=total,
                manifest=None,
            )
        return AdaptiveDualRxPhaseStatusV2(
            session_id=session_id,
            input_manifest_sha256=binding.input_manifest_sha256,
            receiver_ids=receiver_ids,
            state=manifest.state,
            reason=manifest.reason,
            checkpoint_visit_count=manifest.checkpoint_visit_count,
            total_visit_count=manifest.total_visit_count,
            manifest=manifest,
        )

    def phase_artifact_v2(
        self,
        session_id: str,
        *,
        glrt_binding_sha256: str,
        artifact_sha256: str,
        probe_stride_ms: int = 120,
    ) -> bytes | None:
        status = self.phase_status_v2(session_id, probe_stride_ms=probe_stride_ms)
        if status is None or status.manifest is None:
            return None
        if status.manifest.glrt_binding_sha256 != glrt_binding_sha256:
            raise ValueError("adaptive phase V2 artifact changed the GLRT binding")
        store = AdaptiveDualRxPhaseStoreV2(self._root, read_only=True)
        try:
            return store.artifact(status.manifest, expected_sha256=artifact_sha256)
        finally:
            store.close()
