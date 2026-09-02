"""Explicit manual queue boundary for the independent Research pipeline lane."""

from __future__ import annotations

import re
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from leo.application.standard_reprocess import (
    StandardReprocessError,
    StandardReprocessNotFound,
    StandardReprocessUnavailable,
)
from leo.catalog import CatalogRepository
from leo.contracts.pipeline_lanes import PipelineLane
from leo.processing import (
    ProcessingService,
    UnsupportedOnlineRecordingManifestError,
    require_online_recording_manifest,
)
from leo.storage import RecordingStore


class ResearchReprocessResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    pipeline_lane: Literal["research"] = "research"
    session_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(pattern=r"^research-[0-9a-f]{32}$")
    pipeline_release_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    previous_research_run_id: str | None = Field(default=None, max_length=128)
    queued_job_count: int = Field(ge=1, le=64)
    scheduling_priority: Literal["lower_than_standard"] = "lower_than_standard"
    state: Literal["queued"] = "queued"


class AnalysisControlStatusV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[2] = 2
    standard_reprocess_enabled: bool
    research_reprocess_enabled: bool


class ResearchReprocessor(Protocol):
    def queue(self, session_id: str) -> ResearchReprocessResultV1: ...


class ResearchReprocessService:
    def __init__(
        self,
        *,
        catalog: CatalogRepository,
        recordings: RecordingStore,
        processing: ProcessingService,
        pipeline_release_id: str,
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", pipeline_release_id) is None:
            raise ValueError("Research reprocessing requires an exact 40-character release SHA")
        self._catalog = catalog
        self._recordings = recordings
        self._processing = processing
        self._pipeline_release_id = pipeline_release_id

    def queue(self, session_id: str) -> ResearchReprocessResultV1:
        if (
            not session_id
            or len(session_id) > 128
            or re.fullmatch(r"[A-Za-z0-9_.:-]+", session_id) is None
        ):
            raise StandardReprocessNotFound("recording not found")
        snapshot = self._catalog.presentation_snapshot(session_id)
        if snapshot is None:
            raise StandardReprocessNotFound("recording not found")
        if snapshot.bundle_uri is None or snapshot.manifest_digest is None:
            raise StandardReprocessError("recording has no locally available raw IQ")
        if self._catalog.active_run_id(session_id, PipelineLane.RESEARCH) is not None:
            raise StandardReprocessError("recording already has an active Research run")
        try:
            bundle = self._recordings.inspect_uri(snapshot.bundle_uri)
            self._recordings.verify(bundle)
        except Exception as error:
            raise StandardReprocessUnavailable(
                f"recording verification failed: {type(error).__name__}"
            ) from error
        if bundle.manifest_sha256 != snapshot.manifest_digest:
            raise StandardReprocessUnavailable("catalog and recording manifest digests disagree")
        try:
            require_online_recording_manifest(bundle.manifest)
        except UnsupportedOnlineRecordingManifestError as error:
            raise StandardReprocessError(str(error)) from error
        raise StandardReprocessError(
            "current recording schemas require the explicit Standard-native action"
        )
