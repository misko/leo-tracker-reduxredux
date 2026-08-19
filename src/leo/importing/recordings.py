"""Convert verified TEST corpus CI16 fixtures into ordinary recording bundles."""

from __future__ import annotations

import json
import platform
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np

from leo.contracts.digests import sha256_digest
from leo.contracts.profile import CaptureProfileRevisionV1, CaptureProfileV1
from leo.contracts.radio import (
    IqBlockMetadataV1,
    NanosecondIntervalV1,
    RadioIdentityV1,
    RadioSettingsV1,
    ReceiverGainV1,
)
from leo.contracts.recording import (
    CompressionSettingsV1,
    HostIdentityV1,
    ProducerV1,
    RecordingManifestV1,
    RecordingStreamV1,
    StreamTimingV1,
    SynchronizationSummaryV1,
    TimingEstimateV1,
)
from leo.contracts.states import (
    CaptureState,
    ContinuityStatus,
    GainMode,
    RadioTransport,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
    TimingMethod,
)
from leo.domain.iq import IqBlock
from leo.domain.profiles import compile_capture_plan
from leo.importing.corpus import CorpusManifest, FixtureSpec, MaterializationResult
from leo.storage import BundleNotFoundError, RecordingStore

RECORDING_INGEST_SCHEMA = "org.leo.test-recording-ingest/v1"
RECORDING_INGEST_FILENAME = "recording-ingest-v1.json"


class RecordingCorpusIngestError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RecordingIngestResult:
    fixture_id: str
    session_id: str
    bundle_uri: str
    status: Literal["created", "already_present"]


@dataclass(frozen=True, slots=True)
class _IngestStream:
    artifact_id: str
    radio_id: str
    first_sample_utc_ns: int


@dataclass(frozen=True, slots=True)
class _IngestSpec:
    center_frequency_hz: int
    bandwidth_hz: int
    sample_rate_hz: int
    sample_count: int
    receiver_count: Literal[1, 2]
    gain_mode: GainMode
    gains_db: tuple[float, ...]
    timing_uncertainty_ns: int
    streams: tuple[_IngestStream, ...]


@dataclass(frozen=True, slots=True)
class RecordingIngestManifest:
    """Versioned recording geometry kept separate from protected corpus fixtures."""

    corpus_id: str
    source_path: Path
    source_sha256: str
    fixtures: Mapping[str, _IngestSpec]


def load_recording_ingest_manifest(path: Path) -> RecordingIngestManifest:
    """Load the immutable mapping used to turn verified slices into recordings."""

    try:
        payload = path.read_bytes()
        document = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise RecordingCorpusIngestError(
            f"cannot read recording ingest manifest {path}: {error}"
        ) from error
    if not isinstance(document, dict) or set(document) != {
        "schema",
        "corpus_id",
        "fixtures",
    }:
        raise RecordingCorpusIngestError(
            "recording ingest manifest must contain schema, corpus_id, and fixtures"
        )
    if document["schema"] != RECORDING_INGEST_SCHEMA:
        raise RecordingCorpusIngestError(
            f"unsupported recording ingest schema: {document['schema']!r}"
        )
    corpus_id = document["corpus_id"]
    raw_fixtures = document["fixtures"]
    if not isinstance(corpus_id, str) or not corpus_id:
        raise RecordingCorpusIngestError("recording ingest corpus_id must be non-empty")
    if not isinstance(raw_fixtures, list) or not raw_fixtures:
        raise RecordingCorpusIngestError("recording ingest fixtures must be non-empty")
    fixtures: dict[str, _IngestSpec] = {}
    for raw_fixture in raw_fixtures:
        if not isinstance(raw_fixture, dict):
            raise RecordingCorpusIngestError("recording ingest fixture must be an object")
        fixture_id = raw_fixture.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id:
            raise RecordingCorpusIngestError("recording ingest fixture_id must be non-empty")
        if fixture_id in fixtures:
            raise RecordingCorpusIngestError(f"duplicate recording ingest fixture_id: {fixture_id}")
        spec_document = dict(raw_fixture)
        del spec_document["fixture_id"]
        fixtures[fixture_id] = _parse_ingest_spec(spec_document)
    return RecordingIngestManifest(
        corpus_id=corpus_id,
        source_path=path.resolve(strict=True),
        source_sha256=sha256_digest(payload),
        fixtures=fixtures,
    )


class RecordingCorpusIngestService:
    """Publish verified fixture bytes through the normal crash-safe RecordingStore."""

    def __init__(self, recordings: RecordingStore) -> None:
        self.recordings = recordings

    def ingest_required(
        self,
        manifest: CorpusManifest,
        materialized: tuple[MaterializationResult, ...],
        ingest_manifest: RecordingIngestManifest,
    ) -> tuple[RecordingIngestResult, ...]:
        if ingest_manifest.corpus_id != manifest.corpus_id:
            raise RecordingCorpusIngestError("recording ingest and corpus manifest IDs disagree")
        by_id = {item.fixture_id: item for item in materialized}
        required = manifest.required_fixtures()
        required_ids = {item.fixture_id for item in required}
        if set(ingest_manifest.fixtures) != required_ids:
            raise RecordingCorpusIngestError(
                "recording ingest mapping must describe exactly the required fixtures"
            )
        if set(by_id) != required_ids:
            raise RecordingCorpusIngestError(
                "materialized fixture inventory does not match required corpus fixtures"
            )
        return tuple(
            self.ingest(
                manifest,
                fixture,
                by_id[fixture.fixture_id],
                ingest_manifest,
            )
            for fixture in required
        )

    def ingest(
        self,
        manifest: CorpusManifest,
        fixture: FixtureSpec,
        materialized: MaterializationResult,
        ingest_manifest: RecordingIngestManifest,
    ) -> RecordingIngestResult:
        if materialized.fixture_id != fixture.fixture_id:
            raise RecordingCorpusIngestError("fixture and materialization identities disagree")
        try:
            spec = ingest_manifest.fixtures[fixture.fixture_id]
        except KeyError as error:
            raise RecordingCorpusIngestError(
                f"recording ingest mapping lacks required fixture {fixture.fixture_id}"
            ) from error
        artifacts = {item.artifact_id: item for item in fixture.artifacts}
        selected_artifacts = []
        for stream in spec.streams:
            try:
                artifact = artifacts[stream.artifact_id]
            except KeyError as error:
                raise RecordingCorpusIngestError(
                    f"ingest stream references absent artifact: {stream.artifact_id}"
                ) from error
            if artifact.kind != "iq":
                raise RecordingCorpusIngestError(
                    f"ingest stream artifact is not IQ: {stream.artifact_id}"
                )
            expected_bytes = spec.sample_count * spec.receiver_count * 4
            if artifact.selected_byte_count != expected_bytes:
                raise RecordingCorpusIngestError(
                    f"fixture IQ byte geometry disagrees for {stream.artifact_id}: "
                    f"{artifact.selected_byte_count} != {expected_bytes}"
                )
            selected_artifacts.append(artifact)
        if len({stream.radio_id for stream in spec.streams}) != len(spec.streams):
            raise RecordingCorpusIngestError("ingest radio IDs must be unique")

        profile = _profile(manifest, fixture, spec)
        plan = compile_capture_plan(
            CaptureProfileRevisionV1.from_profile(profile),
            tuple(stream.radio_id for stream in spec.streams),
            source_type=SourceType.TEST,
        )
        session_id = fixture.fixture_id
        try:
            existing = self.recordings.inspect(session_id)
        except BundleNotFoundError:
            existing = None
        if existing is not None:
            self.recordings.verify(existing)
            if (
                existing.manifest.source_type is not SourceType.TEST
                or "TEST" not in existing.manifest.tags
                or existing.manifest.capture_plan.plan_digest != plan.plan_digest
            ):
                raise RecordingCorpusIngestError(
                    f"existing recording conflicts with TEST fixture {fixture.fixture_id}"
                )
            return RecordingIngestResult(
                fixture_id=fixture.fixture_id,
                session_id=session_id,
                bundle_uri=existing.uri,
                status="already_present",
            )

        compression = CompressionSettingsV1(policy_id="test-corpus-zstd-128m-v1")
        writer = self.recordings.begin(session_id, compression)
        settings = _settings(spec)
        stream_models: list[RecordingStreamV1] = []
        for index, (stream_spec, artifact) in enumerate(
            zip(spec.streams, selected_artifacts, strict=True)
        ):
            stream_id = f"stream-{index}"
            identity = RadioIdentityV1(
                radio_id=stream_spec.radio_id,
                serial=f"imported-{stream_spec.radio_id}",
                uri=(f"corpus://{manifest.corpus_id}/{fixture.fixture_id}/{artifact.artifact_id}"),
                transport=RadioTransport.IMPORTED,
                model="Imported TEST corpus CI16",
            )
            receiver_ids = tuple(range(spec.receiver_count))
            stream_writer = writer.open_stream(stream_id, identity, receiver_ids)
            path = materialized.directory.joinpath(*artifact.target_relative_path.parts)
            _append_ci16(
                stream_writer,
                path,
                spec,
                stream_spec,
                manifest.corpus_id,
                fixture.fixture_id,
                artifact.selected_sha256,
            )
            receipt = stream_writer.finalize()
            timing = _stream_timing(spec, stream_spec)
            stream_models.append(
                RecordingStreamV1(
                    stream_id=stream_id,
                    radio=identity,
                    requested_settings=settings,
                    applied_settings=settings,
                    state=StreamState.COMPLETE,
                    requested_sample_count=spec.sample_count,
                    captured_sample_count=spec.sample_count,
                    timing=timing,
                    chunks=receipt.chunks,
                    timeline_relative_path=receipt.timeline_relative_path,
                    timeline_sha256=receipt.timeline_sha256,
                    continuity=receipt.continuity,
                )
            )
        synchronization = _synchronization(spec, tuple(stream_models))
        created = min(
            item.timing.first_sample.estimate_utc_ns for item in stream_models if item.timing
        )
        finalized = max(
            item.timing.last_sample.estimate_utc_ns for item in stream_models if item.timing
        )
        published = writer.publish(
            RecordingManifestV1(
                session_id=session_id,
                state=CaptureState.COMMITTED,
                source_type=SourceType.TEST,
                created_utc_ns=created,
                finalized_utc_ns=finalized,
                capture_plan=plan,
                tags=("TEST",),
                streams=tuple(stream_models),
                synchronization=synchronization,
                compression=compression,
                host=HostIdentityV1(
                    hostname=socket.gethostname(),
                    operating_system=platform.platform(),
                ),
                producer=ProducerV1(
                    name="leo-test-corpus-import",
                    version="1",
                    source_revision=ingest_manifest.source_sha256,
                ),
            )
        )
        self.recordings.verify(published)
        return RecordingIngestResult(
            fixture_id=fixture.fixture_id,
            session_id=session_id,
            bundle_uri=published.uri,
            status="created",
        )


def _append_ci16(
    writer: Any,
    path: Path,
    spec: _IngestSpec,
    stream: _IngestStream,
    corpus_id: str,
    fixture_id: str,
    source_digest: str,
) -> None:
    frame_bytes = spec.receiver_count * 4
    block_bytes = 8 * 1024 * 1024
    block_bytes -= block_bytes % frame_bytes
    sample_start = 0
    sequence = 0
    with path.open("rb") as source:
        while payload := source.read(block_bytes):
            if len(payload) % frame_bytes:
                raise RecordingCorpusIngestError(f"CI16 fixture has a partial frame: {path}")
            sample_count = len(payload) // frame_bytes
            estimate = (
                stream.first_sample_utc_ns + sample_start * 1_000_000_000 // spec.sample_rate_hz
            )
            interval = NanosecondIntervalV1(
                lower_ns=max(0, estimate - spec.timing_uncertainty_ns),
                upper_ns=estimate + spec.timing_uncertainty_ns,
            )
            metadata = IqBlockMetadataV1(
                radio_id=stream.radio_id,
                receiver_ids=tuple(range(spec.receiver_count)),
                sample_count=sample_count,
                session_sample_start=sample_start,
                host_request_utc_ns=interval,
                host_request_monotonic_ns=NanosecondIntervalV1(lower_ns=0, upper_ns=0),
                timing_method=TimingMethod.IMPORTED,
                source_sequence=sequence,
                continuity=(
                    ContinuityStatus.UNKNOWN if sequence == 0 else ContinuityStatus.CONTIGUOUS
                ),
                hardware_metadata={
                    "corpus_id": corpus_id,
                    "fixture_id": fixture_id,
                    "selected_sha256": source_digest,
                },
            )
            samples = np.frombuffer(payload, dtype="<i2").reshape(
                sample_count,
                spec.receiver_count,
                2,
            )
            writer.append(IqBlock(samples=samples, metadata=metadata))
            sample_start += sample_count
            sequence += 1
    if sample_start != spec.sample_count:
        raise RecordingCorpusIngestError(
            f"CI16 fixture sample count changed: {sample_start} != {spec.sample_count}"
        )


def _parse_ingest_spec(raw: Mapping[str, Any]) -> _IngestSpec:
    expected_keys = {
        "center_frequency_hz",
        "bandwidth_hz",
        "sample_rate_hz",
        "sample_count",
        "receiver_count",
        "gain_mode",
        "gains_db",
        "timing_uncertainty_ns",
        "streams",
    }
    if set(raw) != expected_keys:
        raise RecordingCorpusIngestError(
            "recording ingest fixture fields differ from the v1 closed schema"
        )
    try:
        receiver_count = int(raw["receiver_count"])
        if receiver_count not in {1, 2}:
            raise ValueError("receiver_count")
        streams_value = raw["streams"]
        if not isinstance(streams_value, list) or not 1 <= len(streams_value) <= 2:
            raise ValueError("streams")
        streams = tuple(
            _IngestStream(
                artifact_id=str(item["artifact_id"]),
                radio_id=str(item["radio_id"]),
                first_sample_utc_ns=int(item["first_sample_utc_ns"]),
            )
            for item in streams_value
            if isinstance(item, Mapping)
        )
        if len(streams) != len(streams_value):
            raise ValueError("streams")
        gain_mode = GainMode(str(raw["gain_mode"]))
        gains_value = raw["gains_db"]
        if not isinstance(gains_value, list):
            raise ValueError("gains_db")
        result = _IngestSpec(
            center_frequency_hz=int(raw["center_frequency_hz"]),
            bandwidth_hz=int(raw["bandwidth_hz"]),
            sample_rate_hz=int(raw["sample_rate_hz"]),
            sample_count=int(raw["sample_count"]),
            receiver_count=cast(Literal[1, 2], receiver_count),
            gain_mode=gain_mode,
            gains_db=tuple(float(value) for value in gains_value),
            timing_uncertainty_ns=int(raw["timing_uncertainty_ns"]),
            streams=streams,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RecordingCorpusIngestError(f"invalid recording ingest fixture: {error}") from error
    positive = (
        result.center_frequency_hz,
        result.bandwidth_hz,
        result.sample_rate_hz,
        result.sample_count,
    )
    if any(value <= 0 for value in positive) or result.timing_uncertainty_ns < 0:
        raise RecordingCorpusIngestError("ingest frequencies/counts must be positive")
    if result.gain_mode is GainMode.MANUAL:
        if len(result.gains_db) != result.receiver_count:
            raise RecordingCorpusIngestError("manual ingest requires gain for every receiver")
    elif result.gains_db:
        raise RecordingCorpusIngestError("automatic-gain ingest cannot declare manual gains")
    return result


def _profile(
    manifest: CorpusManifest,
    fixture: FixtureSpec,
    spec: _IngestSpec,
) -> CaptureProfileV1:
    if len(manifest.corpus_id) > 96:
        raise RecordingCorpusIngestError("corpus ID is too long for capture campaign provenance")
    suffix = sha256_digest(fixture.fixture_id.encode())[7:19]
    name = f"test-{fixture.fixture_id[:76]}-{suffix}"
    receivers = tuple(range(spec.receiver_count))
    gains = tuple(
        ReceiverGainV1(receiver_id=index, gain_db=value)
        for index, value in enumerate(spec.gains_db)
    )
    return CaptureProfileV1(
        name=name,
        description=f"Imported TEST corpus fixture {fixture.fixture_id}",
        center_frequency_hz=spec.center_frequency_hz,
        sample_rate_hz=spec.sample_rate_hz,
        bandwidth_hz=spec.bandwidth_hz,
        receivers=receivers,
        gain_mode=spec.gain_mode,
        gains=gains,
        sample_count=spec.sample_count,
        refill_samples=min(spec.sample_count, 262_144),
        settle_seconds=Decimal(0),
        prime_refills=0,
        synchronization_mode=(
            SynchronizationMode.BEST_EFFORT if len(spec.streams) == 2 else SynchronizationMode.NONE
        ),
        storage_policy="test-corpus-zstd-128m-v1",
        campaign=manifest.corpus_id,
        tags=("TEST",),
    )


def _settings(spec: _IngestSpec) -> RadioSettingsV1:
    return RadioSettingsV1(
        center_frequency_hz=spec.center_frequency_hz,
        sample_rate_hz=spec.sample_rate_hz,
        bandwidth_hz=spec.bandwidth_hz,
        receiver_ids=tuple(range(spec.receiver_count)),
        gain_mode=spec.gain_mode,
        gains=tuple(
            ReceiverGainV1(receiver_id=index, gain_db=value)
            for index, value in enumerate(spec.gains_db)
        ),
    )


def _stream_timing(spec: _IngestSpec, stream: _IngestStream) -> StreamTimingV1:
    last = (
        stream.first_sample_utc_ns + (spec.sample_count - 1) * 1_000_000_000 // spec.sample_rate_hz
    )
    return StreamTimingV1(
        first_sample=_timing_estimate(stream.first_sample_utc_ns, spec.timing_uncertainty_ns),
        last_sample=_timing_estimate(last, spec.timing_uncertainty_ns),
    )


def _timing_estimate(estimate: int, uncertainty: int) -> TimingEstimateV1:
    return TimingEstimateV1(
        estimate_utc_ns=estimate,
        earliest_utc_ns=max(0, estimate - uncertainty),
        latest_utc_ns=estimate + uncertainty,
        method=TimingMethod.IMPORTED,
    )


def _synchronization(
    spec: _IngestSpec,
    streams: tuple[RecordingStreamV1, ...],
) -> SynchronizationSummaryV1:
    stream_ids = tuple(stream.stream_id for stream in streams)
    if len(streams) == 1:
        return SynchronizationSummaryV1(
            requested_mode=SynchronizationMode.NONE,
            effective_mode=SynchronizationMode.NONE,
            grade=SynchronizationGrade.NOT_REQUESTED,
            stream_ids=stream_ids,
        )
    starts = tuple(
        stream.timing.first_sample.estimate_utc_ns for stream in streams if stream.timing
    )
    ends = tuple(stream.timing.last_sample.estimate_utc_ns for stream in streams if stream.timing)
    overlap_start = max(starts)
    overlap_end = min(ends)
    estimated_overlap = max(0, overlap_end - overlap_start)
    uncertainty = spec.timing_uncertainty_ns * 2
    guaranteed = max(0, estimated_overlap - uncertainty)
    duration = max(1, min(end - start for start, end in zip(starts, ends, strict=True)))
    return SynchronizationSummaryV1(
        requested_mode=SynchronizationMode.BEST_EFFORT,
        effective_mode=SynchronizationMode.BEST_EFFORT,
        grade=SynchronizationGrade.BEST_EFFORT_OBSERVED,
        stream_ids=stream_ids,
        estimated_start_skew_ns=max(starts) - min(starts),
        start_skew_uncertainty_ns=uncertainty,
        estimated_overlap_ns=estimated_overlap,
        estimated_overlap_start_utc_ns=overlap_start,
        estimated_overlap_end_utc_ns=overlap_end,
        guaranteed_overlap_ns=guaranteed,
        overlap_fraction=min(1.0, estimated_overlap / duration),
    )
