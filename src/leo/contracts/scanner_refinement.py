"""Additive scanner comparison evidence; existing scan products stay immutable."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol, Self

from pydantic import ConfigDict, Field, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest

Profile = Literal["grid512", "grid8192", "local512", "joint512"]
Case = Literal["baseline", "frequency", "delay"]
Artifact = Literal["shift-recovery", "probe-comparison"]
SessionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
PROFILES: tuple[Profile, ...] = ("grid512", "grid8192", "local512", "joint512")
ARTIFACTS: tuple[Artifact, ...] = ("shift-recovery", "probe-comparison")


class ComparisonCandidateV1(ContractModel):
    model_config = ConfigDict(allow_inf_nan=False)
    rank: int
    integer_epoch_s: float
    epoch_s: float | None
    cfo_hz: float | None
    exact_score: float | None
    margin: float | None


class ComparisonRowV1(ContractModel):
    schema_version: Literal[1] = 1
    probe_id: str
    visit_index: int
    receiver_id: Literal[0, 1]
    target_index: Annotated[int, Field(ge=0, le=7)]
    time_s: float
    profile: Profile
    case: Case
    amount: float
    candidates: Annotated[tuple[ComparisonCandidateV1, ...], Field(max_length=8)]
    selected_rank: int | None
    acquisition_seconds: Annotated[float, Field(ge=0)]
    scoring_seconds: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def _selection_exists(self) -> Self:
        if len({c.rank for c in self.candidates}) != len(self.candidates):
            raise ValueError("comparison candidate ranks must be unique")
        if self.selected_rank is not None and (
            self.selected is None or self.selected.epoch_s is None or self.selected.cfo_hz is None
        ):
            raise ValueError("comparison selected candidate is unavailable")
        return self

    @property
    def selected(self) -> ComparisonCandidateV1 | None:
        return next((c for c in self.candidates if c.rank == self.selected_rank), None)


class ComparisonEvidenceV1(ContractModel):
    schema_version: Literal[1] = 1
    analysis_id: Literal["scanner-local-joint-shift-comparison-v1"] = (
        "scanner-local-joint-shift-comparison-v1"
    )
    session_id: SessionId
    session_kind: Literal["fixed", "adaptive"]
    input_manifest_sha256: Sha256Digest
    implementation_sha256: Sha256Digest
    sample_rate_hz: Literal[2500000, 5000000]
    scheduled_probe_ids: Annotated[tuple[str, ...], Field(max_length=32)]
    rows: Annotated[tuple[ComparisonRowV1, ...], Field(max_length=384)]
    failures: tuple[str, ...] = ()
    window_ms: Literal[20] = 20
    source_read_ms: Literal[21] = 21
    selection_policy: Literal["two-evenly-spaced-visits-per-target-both-receivers"] = (
        "two-evenly-spaced-visits-per-target-both-receivers"
    )

    @model_validator(mode="after")
    def _inventory(self) -> Self:
        if len(set(self.scheduled_probe_ids)) != len(self.scheduled_probe_ids):
            raise ValueError("comparison schedule contains duplicate probes")
        keys = [(r.probe_id, r.case, r.profile) for r in self.rows]
        probes = {r.probe_id for r in self.rows}
        if len(keys) != len(set(keys)) or not probes <= set(self.scheduled_probe_ids):
            raise ValueError("comparison rows contain duplicate or unscheduled cases")
        expected = {
            (p, c, f) for p in probes for c in ("baseline", "frequency", "delay") for f in PROFILES
        }
        if set(keys) != expected:
            raise ValueError("comparison probe lacks a complete profile/case inventory")
        failed = [failure.split("|", 1)[0] for failure in self.failures]
        if (
            len(set(failed)) != len(failed)
            or not set(failed) <= set(self.scheduled_probe_ids)
            or set(failed) & probes
        ):
            raise ValueError("comparison failures must identify distinct unfinished probes")
        return self


class ComparisonMetricV1(ContractModel):
    profile: Profile
    case: Literal["frequency", "delay"]
    attempted: int
    recovered: int
    common: int
    cfo_rms_hz: float | None
    raw_cfo_rms_hz: float | None
    delay_rms_ns: float | None
    alias_changes: int


class ComparisonArtifactV1(ContractModel):
    name: Artifact
    sha256: Sha256Digest
    byte_count: Annotated[int, Field(gt=0, le=8 * 1024 * 1024)]


class ComparisonManifestV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    input_manifest_sha256: Sha256Digest
    evidence_sha256: Sha256Digest
    sample_rate_hz: Literal[2500000, 5000000]
    scheduled_probes: int
    completed_probes: int
    failed_probes: int
    metrics: tuple[ComparisonMetricV1, ...]
    artifacts: tuple[ComparisonArtifactV1, ...]


class ComparisonStatusV1(ContractModel):
    schema_version: Literal[1] = 1
    session_id: SessionId
    state: Literal["not_started", "partial", "complete"]
    manifest: ComparisonManifestV1 | None = None


class ScannerRefinementReader(Protocol):
    def status(self, session_id: str) -> ComparisonStatusV1: ...

    def artifact(self, session_id: str, name: Artifact) -> bytes | None: ...

    def evidence(self, session_id: str) -> bytes | None: ...
