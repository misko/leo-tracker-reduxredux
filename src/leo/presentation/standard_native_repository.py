"""Read-only union port for definition-dispatched Standard presentation."""

from __future__ import annotations

from typing import Protocol

from leo.presentation.standard_native_artifacts import (
    StandardNativePngArtifactInventoryV4,
    StandardNativePngArtifactInventoryV5,
)
from leo.presentation.standard_native_pipeline import (
    StandardNativePlotViewV3,
    StandardNativePlotViewV4,
    StandardNativeSourceProofV3,
    StandardNativeSubjectDetailV3,
    StandardNativeSubjectDetailV4,
    StandardNativeSubjectHierarchyV3,
    StandardNativeSubjectHierarchyV4,
)
from leo.presentation.standard_pipeline import (
    StandardPlotViewV2,
    StandardReplayAuditV1,
    StandardSourceExtremaProofV2,
    StandardSubjectDetailV2,
    StandardSubjectHierarchyV2,
    StandardTrackGateAuditV1,
    StandardViewKindV2,
)


class DefinitionDispatchedStandardPresentationPort(Protocol):
    def subject_hierarchy(
        self, session_id: str
    ) -> (
        StandardSubjectHierarchyV2
        | StandardNativeSubjectHierarchyV3
        | StandardNativeSubjectHierarchyV4
        | None
    ): ...

    def subject_detail(
        self, session_id: str, subject_id: str
    ) -> (
        StandardSubjectDetailV2
        | StandardNativeSubjectDetailV3
        | StandardNativeSubjectDetailV4
        | None
    ): ...

    def subject_replay_audit(
        self, session_id: str, subject_id: str
    ) -> StandardReplayAuditV1 | None: ...

    def subject_track_gate_audit(
        self, session_id: str, subject_id: str
    ) -> StandardTrackGateAuditV1 | None: ...

    def subject_view(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        *,
        maximum_points: int,
    ) -> StandardPlotViewV2 | StandardNativePlotViewV3 | StandardNativePlotViewV4 | None: ...

    def verify_source_extrema(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardSourceExtremaProofV2,
    ) -> bool: ...

    def verify_source_proof(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
        proof: StandardNativeSourceProofV3,
    ) -> bool: ...

    def subject_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        view_kind: StandardViewKindV2,
    ) -> bytes | None: ...

    def subject_png_inventory(
        self,
        session_id: str,
        subject_id: str,
    ) -> StandardNativePngArtifactInventoryV4 | StandardNativePngArtifactInventoryV5 | None: ...

    def subject_named_png_artifact(
        self,
        session_id: str,
        subject_id: str,
        artifact_name: str,
    ) -> bytes | None: ...
