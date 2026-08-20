"""Narrow application service for explicitly requested Standard re-analysis."""

from __future__ import annotations

import re
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from leo.catalog import ActiveRunExistsError, CatalogRepository
from leo.pipeline import compile_standard_run_plan
from leo.presentation.standard_pipeline import StandardSourceTypeV2, standard_eligibility_v2
from leo.processing import ProcessingService
from leo.storage import RecordingStore


class StandardReprocessError(RuntimeError):
    """Base error carrying an HTTP-compatible failure category."""

    status_code = 409


class StandardReprocessNotFound(StandardReprocessError):
    status_code = 404


class StandardReprocessUnavailable(StandardReprocessError):
    status_code = 503


class StandardReprocessResultV1(BaseModel):
    """Bounded acknowledgement for one newly queued immutable analysis run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    session_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(pattern=r"^reprocess-[0-9a-f]{32}$")
    pipeline_release_id: str = Field(pattern=r"^[0-9a-f]{40}$")
    previous_current_run_id: str | None = Field(default=None, max_length=128)
    queued_job_count: int = Field(ge=1, le=64)
    state: Literal["queued"] = "queued"


class StandardReprocessor(Protocol):
    def queue(self, session_id: str) -> StandardReprocessResultV1: ...


class StandardReprocessService:
    """Verify raw authority and enqueue the manifest-derived Standard graph.

    The existing current run is deliberately left untouched. Catalog promotion
    occurs only after the new run completes and seals successfully.
    """

    def __init__(
        self,
        *,
        catalog: CatalogRepository,
        recordings: RecordingStore,
        processing: ProcessingService,
        pipeline_release_id: str,
    ) -> None:
        if re.fullmatch(r"[0-9a-f]{40}", pipeline_release_id) is None:
            raise ValueError("Standard reprocessing requires an exact 40-character release SHA")
        self._catalog = catalog
        self._recordings = recordings
        self._processing = processing
        self._pipeline_release_id = pipeline_release_id

    def queue(self, session_id: str) -> StandardReprocessResultV1:
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
        if self._catalog.active_run_id(session_id) is not None:
            raise StandardReprocessError("recording already has an active analysis run")

        try:
            bundle = self._recordings.inspect_uri(snapshot.bundle_uri)
            self._recordings.verify(bundle)
        except Exception as error:
            raise StandardReprocessUnavailable(
                f"recording verification failed: {type(error).__name__}"
            ) from error
        if bundle.manifest_sha256 != snapshot.manifest_digest:
            raise StandardReprocessUnavailable("catalog and recording manifest digests disagree")
        healthy = all(
            stream.captured_sample_count > 0 and bool(stream.chunks)
            for stream in bundle.manifest.streams
        )
        eligibility = standard_eligibility_v2(
            StandardSourceTypeV2(bundle.manifest.source_type.value.upper()),
            bundle.manifest.tags,
            capture_committed=bundle.manifest.state.value == "committed",
            capture_healthy=healthy,
        )
        if not eligibility.explicit_eligible:
            raise StandardReprocessError(eligibility.reason)
        try:
            release = self._catalog.pipeline_release_snapshot(self._pipeline_release_id)
        except Exception as error:
            raise StandardReprocessUnavailable(
                "deployed analysis release is unavailable"
            ) from error
        if release.code_revision != self._pipeline_release_id:
            raise StandardReprocessUnavailable(
                "deployed analysis release is not exact source authority"
            )

        plan = compile_standard_run_plan(
            bundle.manifest,
            manifest_digest=snapshot.manifest_digest,
            pipeline_release_id=self._pipeline_release_id,
        )
        run_id = f"reprocess-{uuid4().hex}"
        previous = self._catalog.current_run_id(session_id)
        try:
            self._processing.create_expanded_run(
                run_id=run_id,
                plan=plan,
                trigger="reprocess",
                promotion_policy=(
                    "evidence_only" if bundle.manifest.source_type.value == "test" else "current"
                ),
            )
        except ActiveRunExistsError as error:
            raise StandardReprocessError("recording already has an active analysis run") from error
        return StandardReprocessResultV1(
            session_id=session_id,
            run_id=run_id,
            pipeline_release_id=self._pipeline_release_id,
            previous_current_run_id=previous,
            queued_job_count=len(plan.jobs),
        )
