"""SQLAlchemy mappings for the stable PostgreSQL catalog schema."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from leo.catalog.states import AnalysisRunState, JobState

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _json_default() -> Any:
    return text("'{}'::jsonb")


class Radio(Base):
    __tablename__ = "radio"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    serial: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReceiverPath(Base):
    __tablename__ = "receiver_path"
    __table_args__ = (UniqueConstraint("radio_id", "receiver_id", "physical_receiver_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    radio_id: Mapped[str] = mapped_column(
        ForeignKey("radio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    receiver_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str | None] = mapped_column(String(128))
    physical_receiver_id: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )


class HardwareEpoch(Base):
    __tablename__ = "hardware_epoch"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    radio_id: Mapped[str] = mapped_column(
        ForeignKey("radio.id", ondelete="CASCADE"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    ended_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )


class FrequencyCalibration(Base):
    __tablename__ = "frequency_calibration"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    receiver_path_id: Mapped[int] = mapped_column(
        ForeignKey("receiver_path.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hardware_epoch_id: Mapped[int | None] = mapped_column(
        ForeignKey("hardware_epoch.id", ondelete="SET NULL"), index=True
    )
    center_offset_hz: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty_hz: Mapped[float | None] = mapped_column(Float)
    uncertainty_lower_hz: Mapped[float | None] = mapped_column(Float)
    uncertainty_upper_hz: Mapped[float | None] = mapped_column(Float)
    valid_from_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    valid_until_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_uri: Mapped[str | None] = mapped_column(Text)
    evidence_digest: Mapped[str | None] = mapped_column(String(71))
    calibration_digest: Mapped[str | None] = mapped_column(String(71), unique=True)
    method: Mapped[str | None] = mapped_column(String(128))
    created_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FrequencyCalibrationSet(Base):
    __tablename__ = "frequency_calibration_set"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    digest: Mapped[str] = mapped_column(String(71), nullable=False, unique=True)
    evidence_uri: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    promotion_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    sealed_utc_ns: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FrequencyCalibrationSetMember(Base):
    __tablename__ = "frequency_calibration_set_member"
    __table_args__ = (UniqueConstraint("set_id", "ordinal"),)

    set_id: Mapped[str] = mapped_column(
        ForeignKey("frequency_calibration_set.id", ondelete="RESTRICT"), primary_key=True
    )
    calibration_id: Mapped[int] = mapped_column(
        ForeignKey("frequency_calibration.id", ondelete="RESTRICT"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class CaptureProfile(Base):
    __tablename__ = "capture_profile"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CaptureProfileRevision(Base):
    __tablename__ = "capture_profile_revision"
    __table_args__ = (
        UniqueConstraint("profile_id", "revision_number"),
        UniqueConstraint("profile_id", "digest"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("capture_profile.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    digest: Mapped[str] = mapped_column(String(71), nullable=False)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CaptureSession(Base):
    __tablename__ = "capture_session"
    __table_args__ = (
        CheckConstraint("source_type IN ('live', 'test', 'import')", name="source_type_values"),
        CheckConstraint(
            "state IN ('committed', 'degraded', 'failed', 'purging', 'purged')",
            name="state_values",
        ),
        CheckConstraint("allocated_bytes >= 0", name="nonnegative_allocated_bytes"),
        CheckConstraint(
            "(state = 'purging' AND purge_claim_token IS NOT NULL "
            "AND purge_claim_expires_at IS NOT NULL AND purge_previous_state IS NOT NULL) "
            "OR (state <> 'purging' AND purge_claim_token IS NULL "
            "AND purge_claim_expires_at IS NULL AND purge_previous_state IS NULL)",
            name="purge_claim_coherent",
        ),
        Index("ix_capture_session_created_source_state", "created_at", "source_type", "state"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("capture_profile_revision.id", ondelete="RESTRICT"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bundle_uri: Mapped[str | None] = mapped_column(Text)
    manifest_digest: Mapped[str | None] = mapped_column(String(71))
    allocated_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    raw_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    purge_claim_token: Mapped[str | None] = mapped_column(String(128))
    purge_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_previous_state: Mapped[str | None] = mapped_column(String(16))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class RadioStream(Base):
    __tablename__ = "radio_stream"
    __table_args__ = (UniqueConstraint("session_id", "radio_id"),)

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    radio_id: Mapped[str] = mapped_column(
        ForeignKey("radio.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    receiver_ids: Mapped[list[int]] = mapped_column(ARRAY(SmallInteger), nullable=False)
    sample_rate_hz: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    observed_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )


class RecordingChunk(Base):
    __tablename__ = "recording_chunk"
    __table_args__ = (UniqueConstraint("stream_id", "chunk_index"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    stream_id: Mapped[str] = mapped_column(
        ForeignKey("radio_stream.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sample_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    logical_uri: Mapped[str] = mapped_column(Text, nullable=False)
    compressed_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    uncompressed_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    compressed_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uncompressed_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Tag(Base):
    __tablename__ = "tag"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)


class SessionTag(Base):
    __tablename__ = "session_tag"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), primary_key=True
    )
    tag_name: Mapped[str] = mapped_column(
        ForeignKey("tag.name", ondelete="CASCADE"), primary_key=True
    )


class RetentionHold(Base):
    __tablename__ = "retention_hold"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "uq_retention_hold_active_session",
            "session_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
        ),
    )


class RetentionEvent(Base):
    __tablename__ = "retention_event"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("capture_session.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    bytes_reclaimed: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class PipelineRelease(Base):
    __tablename__ = "pipeline_release"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    code_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    environment_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    graph_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_run"
    __table_args__ = (
        CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="state_values",
        ),
        CheckConstraint(
            "promotion_policy IN ('current', 'evidence_only')",
            name="promotion_policy_values",
        ),
        Index(
            "uq_analysis_run_active_session",
            "session_id",
            unique=True,
            postgresql_where=text("state IN ('pending', 'running')"),
        ),
        Index("ix_analysis_run_session_created", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), nullable=False
    )
    pipeline_release_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_release.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    promotion_policy: Mapped[str] = mapped_column(
        String(16), nullable=False, default="current", server_default="current"
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AnalysisRunState.PENDING.value
    )
    input_manifest_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manifest_uri: Mapped[str | None] = mapped_column(Text)
    manifest_digest: Mapped[str | None] = mapped_column(String(71))
    failure: Mapped[str | None] = mapped_column(Text)


class ProcessingJob(Base):
    __tablename__ = "processing_job"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", "scope_key"),
        CheckConstraint(
            "state IN ('pending', 'leased', 'succeeded', 'failed', 'cancelled')",
            name="state_values",
        ),
        CheckConstraint("max_attempts > 0", name="positive_max_attempts"),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
        CheckConstraint(
            "(state = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (state <> 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)",
            name="lease_state_coherence",
        ),
        Index("ix_processing_job_claim", "state", "available_at", "priority", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False, default="session")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default=JobState.PENDING.value)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class ProcessingJobDependency(Base):
    __tablename__ = "processing_job_dependency"
    __table_args__ = (CheckConstraint("job_id <> depends_on_job_id", name="not_self"),)

    job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_job.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_job.id", ondelete="CASCADE"), primary_key=True
    )


class ProcessingJobAttempt(Base):
    __tablename__ = "processing_job_attempt"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("processing_job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)


class AnalysisProduct(Base):
    __tablename__ = "analysis_product"
    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", "scope_key", "kind", "schema_version"),
        CheckConstraint("schema_version > 0", name="positive_schema_version"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        CheckConstraint(
            "(purge_claim_token IS NULL AND purge_claim_expires_at IS NULL) OR "
            "(purge_claim_token IS NOT NULL AND purge_claim_expires_at IS NOT NULL)",
            name="purge_claim_coherent",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_run.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False, default="session")
    kind: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    logical_uri: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(String(71), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    purge_claim_token: Mapped[str | None] = mapped_column(String(128))
    purge_claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ScientificCampaign(Base):
    """Durable WP11 campaign identity and its sealed aggregate evidence."""

    __tablename__ = "scientific_campaign"
    __table_args__ = (
        CheckConstraint(
            "state <> 'sealed' OR seal_authority_version = 0 OR "
            "(outer_seal_uri IS NOT NULL AND outer_seal_digest IS NOT NULL)",
            name="scientific_campaign_outer_seal_authority",
        ),
        CheckConstraint("state IN ('in_progress', 'sealed')", name="state_values"),
        CheckConstraint(
            "result_status IS NULL OR result_status IN ('pass', 'fail', 'inconclusive')",
            name="result_status_values",
        ),
        CheckConstraint("expected_stream_count = 40", name="exact_stream_count"),
        CheckConstraint(
            "(state = 'in_progress' AND sealed_at IS NULL "
            "AND scientific_uri IS NULL AND scientific_digest IS NULL "
            "AND presentation_uri IS NULL AND presentation_digest IS NULL "
            "AND result_status IS NULL) OR "
            "(state = 'sealed' AND sealed_at IS NOT NULL "
            "AND scientific_uri IS NOT NULL AND scientific_digest IS NOT NULL "
            "AND presentation_uri IS NOT NULL AND presentation_digest IS NOT NULL "
            "AND result_status IS NOT NULL)",
            name="seal_coherent",
        ),
    )

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="in_progress", server_default="in_progress"
    )
    expected_stream_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=40, server_default="40"
    )
    capture_uri: Mapped[str] = mapped_column(Text, nullable=False)
    capture_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    scientific_uri: Mapped[str | None] = mapped_column(Text)
    scientific_digest: Mapped[str | None] = mapped_column(String(71))
    presentation_uri: Mapped[str | None] = mapped_column(Text)
    presentation_digest: Mapped[str | None] = mapped_column(String(71))
    outer_seal_uri: Mapped[str | None] = mapped_column(Text)
    outer_seal_digest: Mapped[str | None] = mapped_column(String(71))
    seal_authority_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    result_status: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScientificCampaignStream(Base):
    """One exact captured stream and all catalog evidence bound to it."""

    __tablename__ = "scientific_campaign_stream"
    __table_args__ = (
        UniqueConstraint("campaign_id", "ordinal"),
        UniqueConstraint("campaign_id", "session_id", "stream_id"),
        UniqueConstraint("campaign_id", "analysis_product_id"),
        CheckConstraint("ordinal >= 0 AND ordinal < 40", name="ordinal_range"),
        CheckConstraint(
            "status IN ('pass', 'fail', 'inconclusive', 'insufficient')",
            name="status_values",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        ForeignKey("scientific_campaign.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stream_id: Mapped[str] = mapped_column(
        ForeignKey("radio_stream.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_run.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_run_uri: Mapped[str] = mapped_column(Text, nullable=False)
    analysis_run_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    pipeline_release_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_release.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    analysis_product_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_product.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    frequency_calibration_id: Mapped[int] = mapped_column(
        ForeignKey("frequency_calibration.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    capture_uri: Mapped[str] = mapped_column(Text, nullable=False)
    capture_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    calibration_uri: Mapped[str] = mapped_column(Text, nullable=False)
    calibration_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    scientific_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scientific_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProductDependency(Base):
    __tablename__ = "product_dependency"
    __table_args__ = (CheckConstraint("product_id <> input_product_id", name="not_self"),)

    product_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_product.id", ondelete="CASCADE"), primary_key=True
    )
    input_product_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_product.id", ondelete="RESTRICT"), primary_key=True
    )


class CurrentAnalysis(Base):
    __tablename__ = "current_analysis"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_run.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class AnalysisSummary(Base):
    __tablename__ = "analysis_summary"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("capture_session.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_run.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    mean_power_dbfs: Mapped[float | None] = mapped_column(Float, index=True)
    best_qam_accuracy: Mapped[float | None] = mapped_column(Float, index=True)
    best_cfo_hz: Mapped[float | None] = mapped_column(Float, index=True)
    doppler_slope_hz_s: Mapped[float | None] = mapped_column(Float, index=True)
    candidate_count: Mapped[int | None] = mapped_column(Integer, index=True)
    coverage: Mapped[float | None] = mapped_column(Float, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=_json_default()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
