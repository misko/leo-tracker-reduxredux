"""Offline acceptance of independent and synchronized single-RX capture modes."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import uuid4

import numpy as np
from pydantic import Field, StringConstraints, field_validator, model_validator

from leo.contracts.base import ContractModel
from leo.contracts.digests import Sha256Digest
from leo.contracts.profile import CaptureProfileRevisionV1
from leo.contracts.states import (
    CaptureState,
    GainMode,
    SourceType,
    StreamState,
    SynchronizationGrade,
    SynchronizationMode,
)
from leo.pipeline.contracts import IqReader
from leo.storage import RecordingStore

CaptureModeRole = Literal["independent_radio_a", "independent_radio_b", "synchronized_pair"]
_HARDWARE_PROFILE_NAME = "starlink-ch4-lower-2p5m-60s-rx1"
_HARDWARE_PROFILE_REVISION_DIGEST = (
    "sha256:7dfcdb9a83794f0a24486558a3f1d3b4bbff1b1ea4c97a94d0828a4490086af0"
)
_HARDWARE_IF_HZ = 1_709_687_500
_HARDWARE_RF_HZ = 11_459_687_500
_HARDWARE_SAMPLE_RATE_HZ = 2_500_000
_HARDWARE_BANDWIDTH_HZ = 2_500_000
_HARDWARE_SAMPLE_COUNT = 150_000_000
_HARDWARE_RECEIVER_ID = 1
_HARDWARE_GAIN_DB = 40.0
_HARDWARE_MINIMUM_OVERLAP = 0.99
SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]


class CaptureModeExpectationV1(ContractModel):
    """Exact geometry shared by the three hardware-acceptance sessions."""

    schema_version: Literal[1] = 1
    profile_name: str
    profile_revision_digest: Sha256Digest
    radio_ids: tuple[SafeIdentifier, SafeIdentifier]
    receiver_id: Annotated[int, Field(ge=0, le=1)]
    center_frequency_hz: Annotated[int, Field(gt=0)]
    rf_center_frequency_hz: Annotated[int, Field(gt=0)]
    sample_rate_hz: Annotated[int, Field(gt=0)]
    bandwidth_hz: Annotated[int, Field(gt=0)]
    gain_db: Annotated[float, Field(ge=40.0, le=40.0)]
    sample_count: Annotated[int, Field(gt=0)]
    starlink_channel: Literal["ch4"] = "ch4"
    starlink_edge: Literal["lower"] = "lower"
    requested_synchronization_mode: Literal[SynchronizationMode.BEST_EFFORT] = (
        SynchronizationMode.BEST_EFFORT
    )
    minimum_pair_overlap_fraction: Annotated[float, Field(ge=0.0, le=1.0)] = 0.99
    clipping_abs_threshold: Annotated[int, Field(ge=1, le=32_768)] = 32_767
    maximum_clipped_sample_fraction: Annotated[float, Field(ge=0.0, le=0.0)] = 0.0
    maximum_gap_count: Literal[0] = 0
    maximum_missing_sample_count: Literal[0] = 0
    maximum_overflow_count: Literal[0] = 0
    maximum_constant_iq_stream_count: Literal[0] = 0
    source_type: SourceType = SourceType.LIVE

    @field_validator("radio_ids")
    @classmethod
    def _radio_ids_are_distinct(cls, value: tuple[str, str]) -> tuple[str, str]:
        if len(set(value)) != 2:
            raise ValueError("capture-mode acceptance requires two distinct radios")
        return value

    @classmethod
    def from_profile_revision(
        cls,
        revision: CaptureProfileRevisionV1,
        radio_ids: tuple[str, str],
        *,
        source_type: SourceType = SourceType.LIVE,
        minimum_pair_overlap_fraction: float = 0.99,
    ) -> Self:
        profile = revision.profile
        if profile.duration_seconds is None or profile.sample_count is not None:
            raise ValueError("capture-mode acceptance profile requires a duration")
        if profile.rf_center_frequency_hz is None:
            raise ValueError("capture-mode acceptance profile requires an RF center")
        if (
            profile.starlink_channel != "ch4"
            or getattr(profile.starlink_edge, "value", None) != "lower"
        ):
            raise ValueError("capture-mode acceptance profile must target CH4 lower")
        if len(profile.receivers) != 1:
            raise ValueError("capture-mode acceptance profile must select exactly one RX")
        if profile.gain_mode is not GainMode.MANUAL or len(profile.gains) != 1:
            raise ValueError("capture-mode acceptance profile requires one manual RX gain")
        gain = profile.gains[0]
        if gain.receiver_id != profile.receivers[0]:
            raise ValueError("capture-mode acceptance gain does not match its RX")
        if gain.gain_db != 40.0:
            raise ValueError("capture-mode acceptance profile requires frozen 40 dB gain")
        sample_count = int(profile.duration_seconds * profile.sample_rate_hz)
        return cls(
            profile_name=profile.name,
            profile_revision_digest=revision.revision_digest,
            radio_ids=radio_ids,
            receiver_id=profile.receivers[0],
            center_frequency_hz=profile.center_frequency_hz,
            rf_center_frequency_hz=profile.rf_center_frequency_hz,
            sample_rate_hz=profile.sample_rate_hz,
            bandwidth_hz=profile.bandwidth_hz,
            gain_db=gain.gain_db,
            sample_count=sample_count,
            minimum_pair_overlap_fraction=minimum_pair_overlap_fraction,
            source_type=source_type,
        )

    @classmethod
    def from_hardware_profile_revision(
        cls,
        revision: CaptureProfileRevisionV1,
        radio_ids: tuple[str, str],
    ) -> Self:
        if revision.profile.duration_seconds != 60 or revision.profile.sample_count is not None:
            raise ValueError("hardware capture-mode campaign requires an exact 60 second dwell")
        expectation = cls.from_profile_revision(
            revision,
            radio_ids,
            source_type=SourceType.LIVE,
            minimum_pair_overlap_fraction=_HARDWARE_MINIMUM_OVERLAP,
        )
        _require_hardware_expectation(expectation)
        return expectation


class CaptureModeSessionCheckV1(ContractModel):
    schema_version: Literal[1] = 1
    role: CaptureModeRole
    session_id: SafeIdentifier
    expected_radio_ids: tuple[SafeIdentifier, ...]
    bundle_uri: str | None = None
    manifest_sha256: Sha256Digest | None = None
    digest_valid: bool = False
    observed_radio_ids: tuple[str, ...] = ()
    observed_receiver_ids: tuple[tuple[int, ...], ...] = ()
    observed_sample_counts: tuple[int, ...] = ()
    observed_gain_db: tuple[float, ...] = ()
    observed_gap_counts: tuple[int, ...] = ()
    observed_missing_sample_counts: tuple[int, ...] = ()
    observed_overflow_counts: tuple[int, ...] = ()
    observed_clipped_sample_counts: tuple[int, ...] = ()
    observed_clipped_sample_fractions: tuple[Annotated[float, Field(ge=0.0, le=1.0)], ...] = ()
    observed_constant_iq: tuple[bool, ...] = ()
    synchronization_grade: SynchronizationGrade | None = None
    overlap_fraction: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    passed: bool = False
    errors: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _passed_has_no_errors(self) -> Self:
        if self.passed != (self.digest_valid and not self.errors):
            raise ValueError("capture-mode check pass state disagrees with evidence")
        return self


class CaptureModeAcceptanceReceiptV1(ContractModel):
    kind: Literal["single_rx_capture_mode_acceptance"] = "single_rx_capture_mode_acceptance"
    schema_version: Literal[1] = 1
    acceptance_id: SafeIdentifier
    observed_utc_ns: Annotated[int, Field(ge=0)]
    expectation: CaptureModeExpectationV1
    checks: tuple[CaptureModeSessionCheckV1, CaptureModeSessionCheckV1, CaptureModeSessionCheckV1]
    accepted: bool
    acceptance_scope: Literal["capture_only"] = "capture_only"
    processing_evidence_evaluated: Literal[False] = False
    scientific_acceptance_claimed: Literal[False] = False
    required_follow_up: Literal["linked_standard_processing_and_detection_receipt"] = (
        "linked_standard_processing_and_detection_receipt"
    )

    @model_validator(mode="after")
    def _receipt_is_complete(self) -> Self:
        expected_roles: tuple[CaptureModeRole, ...] = (
            "independent_radio_a",
            "independent_radio_b",
            "synchronized_pair",
        )
        if tuple(check.role for check in self.checks) != expected_roles:
            raise ValueError("capture-mode receipt requires the three canonical roles")
        session_ids = tuple(check.session_id for check in self.checks)
        if len(set(session_ids)) != 3:
            raise ValueError("capture-mode receipt requires three distinct sessions")
        if self.accepted != all(check.passed for check in self.checks):
            raise ValueError("capture-mode receipt acceptance disagrees with checks")
        return self


class CaptureModeCampaignAcceptanceReceiptV2(ContractModel):
    """Ten trials in each canonical capture stratum (30 distinct sessions)."""

    kind: Literal["single_rx_capture_mode_campaign_acceptance"] = (
        "single_rx_capture_mode_campaign_acceptance"
    )
    schema_version: Literal[2] = 2
    acceptance_id: SafeIdentifier
    observed_utc_ns: Annotated[int, Field(ge=0)]
    expectation: CaptureModeExpectationV1
    trial_receipts: tuple[CaptureModeAcceptanceReceiptV1, ...]
    accepted: bool
    acceptance_scope: Literal["capture_only"] = "capture_only"
    processing_evidence_evaluated: Literal[False] = False
    scientific_acceptance_claimed: Literal[False] = False
    required_follow_up: Literal["linked_standard_processing_and_detection_receipt"] = (
        "linked_standard_processing_and_detection_receipt"
    )

    @model_validator(mode="after")
    def _campaign_is_complete(self) -> Self:
        _require_hardware_expectation(self.expectation)
        if len(self.trial_receipts) != 10:
            raise ValueError("capture-mode campaign requires exactly 10 trials per stratum")
        if any(receipt.expectation != self.expectation for receipt in self.trial_receipts):
            raise ValueError("capture-mode campaign trial expectations differ")
        session_ids = tuple(
            check.session_id for receipt in self.trial_receipts for check in receipt.checks
        )
        if len(session_ids) != 30 or len(set(session_ids)) != 30:
            raise ValueError("capture-mode campaign requires 30 distinct sessions")
        trial_ids = tuple(receipt.acceptance_id for receipt in self.trial_receipts)
        if len(set(trial_ids)) != 10:
            raise ValueError("capture-mode campaign trial IDs must be distinct")
        if self.accepted != all(receipt.accepted for receipt in self.trial_receipts):
            raise ValueError("capture-mode campaign acceptance disagrees with its trials")
        return self


class CaptureModeAcceptanceHarness:
    """Verify three already-committed bundles without radios or a database."""

    def __init__(self, store: RecordingStore) -> None:
        _reject_qnap_path(store.root)
        _reject_symlinked_path(store.root)
        self._store = store

    @classmethod
    def open_read_only(cls, root: Path) -> Self:
        """Open an existing local store after no-follow QNAP confinement checks."""

        _reject_qnap_path(root)
        _reject_symlinked_path(root)
        return cls(RecordingStore.open_read_only(root))

    def run(
        self,
        expectation: CaptureModeExpectationV1,
        *,
        acceptance_id: str,
        independent_radio_a_session_id: str,
        independent_radio_b_session_id: str,
        synchronized_pair_session_id: str,
        receipt_path: Path | None = None,
        observed_utc_ns: int | None = None,
    ) -> CaptureModeAcceptanceReceiptV1:
        sessions: tuple[tuple[CaptureModeRole, str, tuple[str, ...]], ...] = (
            ("independent_radio_a", independent_radio_a_session_id, (expectation.radio_ids[0],)),
            ("independent_radio_b", independent_radio_b_session_id, (expectation.radio_ids[1],)),
            ("synchronized_pair", synchronized_pair_session_id, expectation.radio_ids),
        )
        if len({session_id for _, session_id, _ in sessions}) != 3:
            raise ValueError("capture-mode acceptance requires three distinct session IDs")
        checks = tuple(
            self._check(expectation, role, session_id, expected_radios)
            for role, session_id, expected_radios in sessions
        )
        receipt = CaptureModeAcceptanceReceiptV1(
            acceptance_id=acceptance_id,
            observed_utc_ns=time.time_ns() if observed_utc_ns is None else observed_utc_ns,
            expectation=expectation,
            checks=checks,  # type: ignore[arg-type]
            accepted=all(check.passed for check in checks),
        )
        if receipt_path is not None:
            _write_immutable_receipt(receipt_path, receipt)
        return receipt

    def run_campaign(
        self,
        expectation: CaptureModeExpectationV1,
        *,
        acceptance_id: str,
        independent_radio_a_session_ids: tuple[str, ...],
        independent_radio_b_session_ids: tuple[str, ...],
        synchronized_pair_session_ids: tuple[str, ...],
        receipt_path: Path | None = None,
        observed_utc_ns: int | None = None,
    ) -> CaptureModeCampaignAcceptanceReceiptV2:
        _require_hardware_expectation(expectation)
        strata = (
            independent_radio_a_session_ids,
            independent_radio_b_session_ids,
            synchronized_pair_session_ids,
        )
        if any(len(session_ids) != 10 for session_ids in strata):
            raise ValueError("capture-mode campaign requires exactly 10 sessions per stratum")
        all_session_ids = tuple(session_id for stratum in strata for session_id in stratum)
        if len(set(all_session_ids)) != 30:
            raise ValueError("capture-mode campaign requires 30 distinct sessions")
        trials = tuple(
            self.run(
                expectation,
                acceptance_id=f"capture-mode-trial-{index:02d}",
                independent_radio_a_session_id=independent_radio_a_session_ids[index],
                independent_radio_b_session_id=independent_radio_b_session_ids[index],
                synchronized_pair_session_id=synchronized_pair_session_ids[index],
            )
            for index in range(10)
        )
        receipt = CaptureModeCampaignAcceptanceReceiptV2(
            acceptance_id=acceptance_id,
            observed_utc_ns=time.time_ns() if observed_utc_ns is None else observed_utc_ns,
            expectation=expectation,
            trial_receipts=trials,
            accepted=all(trial.accepted for trial in trials),
        )
        if receipt_path is not None:
            _write_immutable_receipt(receipt_path, receipt)
        return receipt

    def _check(
        self,
        expectation: CaptureModeExpectationV1,
        role: CaptureModeRole,
        session_id: str,
        expected_radios: tuple[str, ...],
    ) -> CaptureModeSessionCheckV1:
        errors: list[str] = []
        try:
            bundle = self._store.inspect(session_id)
        except Exception as error:
            return CaptureModeSessionCheckV1(
                role=role,
                session_id=session_id,
                expected_radio_ids=expected_radios,
                errors=(f"bundle inspection failed: {type(error).__name__}: {error}",),
            )
        try:
            self._store.verify(bundle)
            digest_valid = True
        except Exception as error:
            digest_valid = False
            errors.append(f"bundle verification failed: {type(error).__name__}: {error}")

        manifest = bundle.manifest
        plan = manifest.capture_plan
        profile = plan.profile_revision.profile
        streams = manifest.streams
        sync = manifest.synchronization
        expected_effective = (
            SynchronizationMode.NONE
            if role != "synchronized_pair"
            else SynchronizationMode.BEST_EFFORT
        )

        _expect(errors, manifest.state is CaptureState.COMMITTED, "session is not committed")
        _expect(errors, manifest.source_type is expectation.source_type, "source type differs")
        _expect(
            errors,
            plan.profile_revision.revision_digest == expectation.profile_revision_digest,
            "profile revision differs",
        )
        _expect(errors, profile.name == expectation.profile_name, "profile name differs")
        _expect(
            errors,
            profile.center_frequency_hz == expectation.center_frequency_hz,
            "IF center differs",
        )
        _expect(
            errors,
            profile.rf_center_frequency_hz == expectation.rf_center_frequency_hz,
            "RF center differs",
        )
        _expect(
            errors,
            profile.starlink_channel == expectation.starlink_channel,
            "Starlink channel differs",
        )
        _expect(
            errors,
            getattr(profile.starlink_edge, "value", None) == expectation.starlink_edge,
            "Starlink edge differs",
        )
        _expect(errors, profile.sample_rate_hz == expectation.sample_rate_hz, "sample rate differs")
        _expect(errors, profile.bandwidth_hz == expectation.bandwidth_hz, "bandwidth differs")
        _expect(errors, profile.gain_mode is GainMode.MANUAL, "profile gain mode differs")
        _expect(
            errors,
            len(profile.gains) == 1 and profile.gains[0].gain_db == expectation.gain_db,
            "profile gain differs",
        )
        _expect(
            errors,
            profile.receivers == (expectation.receiver_id,),
            "profile is not the expected single RX",
        )
        _expect(
            errors,
            plan.resolved_sample_count == expectation.sample_count,
            "plan sample count differs",
        )
        _expect(errors, plan.radio_ids == expected_radios, "capture-plan radios differ")
        _expect(errors, len(streams) == len(expected_radios), "stream count differs")
        _expect(
            errors,
            tuple(stream.radio.radio_id for stream in streams) == expected_radios,
            "stream radios differ",
        )
        _expect(
            errors,
            plan.requested_synchronization_mode is SynchronizationMode.BEST_EFFORT,
            "requested synchronization mode differs",
        )
        _expect(
            errors,
            plan.effective_synchronization_mode is expected_effective,
            "effective synchronization mode differs",
        )
        _expect(
            errors,
            sync.effective_mode is expected_effective,
            "observed synchronization mode differs",
        )

        observed_gains: list[float] = []
        clipped_counts: list[int] = []
        clipped_fractions: list[float] = []
        constant_iq: list[bool] = []
        for index, stream in enumerate(streams):
            settings = stream.applied_settings or stream.requested_settings
            _expect(errors, stream.state is StreamState.COMPLETE, f"stream {index} is not complete")
            _expect(
                errors,
                settings.receiver_ids == (expectation.receiver_id,),
                f"stream {index} receiver geometry differs",
            )
            _expect(
                errors,
                settings.center_frequency_hz == expectation.center_frequency_hz,
                f"stream {index} IF center differs",
            )
            _expect(
                errors,
                settings.sample_rate_hz == expectation.sample_rate_hz,
                f"stream {index} sample rate differs",
            )
            _expect(
                errors,
                settings.bandwidth_hz == expectation.bandwidth_hz,
                f"stream {index} bandwidth differs",
            )
            gain = settings.gains[0] if len(settings.gains) == 1 else None
            observed_gains.append(0.0 if gain is None else gain.gain_db)
            _expect(
                errors, settings.gain_mode is GainMode.MANUAL, f"stream {index} gain mode differs"
            )
            _expect(
                errors,
                gain is not None
                and gain.receiver_id == expectation.receiver_id
                and gain.gain_db == expectation.gain_db,
                f"stream {index} gain differs",
            )
            _expect(
                errors,
                stream.requested_sample_count == expectation.sample_count,
                f"stream {index} requested samples differ",
            )
            _expect(
                errors,
                stream.captured_sample_count == expectation.sample_count,
                f"stream {index} captured samples differ",
            )
            _expect(errors, bool(stream.chunks), f"stream {index} has no IQ chunks")
            _expect(errors, stream.timing is not None, f"stream {index} has no timing evidence")
            continuity = stream.continuity
            _expect(
                errors,
                continuity.gap_count <= expectation.maximum_gap_count,
                f"stream {index} gap count exceeds threshold",
            )
            _expect(
                errors,
                continuity.missing_sample_count <= expectation.maximum_missing_sample_count,
                f"stream {index} missing sample count exceeds threshold",
            )
            _expect(
                errors,
                continuity.overflow_count <= expectation.maximum_overflow_count,
                f"stream {index} overflow count exceeds threshold",
            )
            try:
                clipped_count, clipped_fraction, is_constant = _scan_stream_quality(
                    self._store.reader(bundle, stream.stream_id),
                    clipping_abs_threshold=expectation.clipping_abs_threshold,
                )
            except Exception as error:
                clipped_count, clipped_fraction, is_constant = 0, 0.0, False
                errors.append(
                    f"stream {index} quality scan failed: {type(error).__name__}: {error}"
                )
            clipped_counts.append(clipped_count)
            clipped_fractions.append(clipped_fraction)
            constant_iq.append(is_constant)
            _expect(
                errors,
                clipped_fraction <= expectation.maximum_clipped_sample_fraction,
                f"stream {index} clipped sample fraction exceeds threshold",
            )
            _expect(
                errors,
                int(is_constant) <= expectation.maximum_constant_iq_stream_count,
                f"stream {index} IQ is constant",
            )

        if role == "synchronized_pair":
            _expect(
                errors,
                sync.grade
                in {SynchronizationGrade.BEST_EFFORT_OBSERVED, SynchronizationGrade.DEGRADED},
                "paired synchronization grade is invalid",
            )
            _expect(errors, sync.overlap_fraction is not None, "paired overlap is absent")
            if sync.overlap_fraction is not None:
                _expect(
                    errors,
                    sync.overlap_fraction >= expectation.minimum_pair_overlap_fraction,
                    "paired overlap is below threshold",
                )
        else:
            _expect(
                errors,
                sync.grade is SynchronizationGrade.NOT_REQUESTED,
                "independent session claims synchronization",
            )
            _expect(errors, sync.overlap_fraction is None, "independent session claims overlap")

        canonical_errors = tuple(dict.fromkeys(errors))
        return CaptureModeSessionCheckV1(
            role=role,
            session_id=session_id,
            expected_radio_ids=expected_radios,
            bundle_uri=bundle.uri,
            manifest_sha256=bundle.manifest_sha256,
            digest_valid=digest_valid,
            observed_radio_ids=tuple(stream.radio.radio_id for stream in streams),
            observed_receiver_ids=tuple(
                (stream.applied_settings or stream.requested_settings).receiver_ids
                for stream in streams
            ),
            observed_sample_counts=tuple(stream.captured_sample_count for stream in streams),
            observed_gain_db=tuple(observed_gains),
            observed_gap_counts=tuple(stream.continuity.gap_count for stream in streams),
            observed_missing_sample_counts=tuple(
                stream.continuity.missing_sample_count for stream in streams
            ),
            observed_overflow_counts=tuple(stream.continuity.overflow_count for stream in streams),
            observed_clipped_sample_counts=tuple(clipped_counts),
            observed_clipped_sample_fractions=tuple(clipped_fractions),
            observed_constant_iq=tuple(constant_iq),
            synchronization_grade=sync.grade,
            overlap_fraction=sync.overlap_fraction,
            passed=digest_valid and not canonical_errors,
            errors=canonical_errors,
        )


def _expect(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _require_hardware_expectation(expectation: CaptureModeExpectationV1) -> None:
    required = (
        expectation.profile_name == _HARDWARE_PROFILE_NAME
        and expectation.profile_revision_digest == _HARDWARE_PROFILE_REVISION_DIGEST
        and expectation.receiver_id == _HARDWARE_RECEIVER_ID
        and expectation.center_frequency_hz == _HARDWARE_IF_HZ
        and expectation.rf_center_frequency_hz == _HARDWARE_RF_HZ
        and expectation.sample_rate_hz == _HARDWARE_SAMPLE_RATE_HZ
        and expectation.bandwidth_hz == _HARDWARE_BANDWIDTH_HZ
        and expectation.gain_db == _HARDWARE_GAIN_DB
        and expectation.sample_count == _HARDWARE_SAMPLE_COUNT
        and expectation.source_type is SourceType.LIVE
        and expectation.minimum_pair_overlap_fraction == _HARDWARE_MINIMUM_OVERLAP
    )
    if not required:
        raise ValueError(
            "hardware capture-mode campaign requires the immutable 60s CH4 LOWER RX1 "
            "2.5MS/s 40dB LIVE profile and frozen 0.99 overlap threshold"
        )


def _scan_stream_quality(
    reader: IqReader,
    *,
    clipping_abs_threshold: int,
) -> tuple[int, float, bool]:
    """Compute bounded-memory ADC clipping and constant-IQ evidence from stored CI16."""

    clipped = 0
    observed = 0
    minimum: np.ndarray | None = None
    maximum: np.ndarray | None = None
    for block in reader.iter_blocks(block_samples=262_144):
        values = block.samples[:, 0, :].astype(np.int32, copy=False)
        magnitudes = np.abs(values)
        clipped += int(np.count_nonzero(np.any(magnitudes >= clipping_abs_threshold, axis=1)))
        observed += len(values)
        block_minimum = values.min(axis=0)
        block_maximum = values.max(axis=0)
        minimum = block_minimum if minimum is None else np.minimum(minimum, block_minimum)
        maximum = block_maximum if maximum is None else np.maximum(maximum, block_maximum)
    if observed != reader.sample_count:
        raise ValueError("quality scan does not cover the stored sample count")
    if minimum is None or maximum is None:
        raise ValueError("quality scan observed no IQ samples")
    return clipped, clipped / observed, bool(np.array_equal(minimum, maximum))


def _write_immutable_receipt(
    path: Path,
    receipt: CaptureModeAcceptanceReceiptV1 | CaptureModeCampaignAcceptanceReceiptV2,
) -> None:
    _reject_qnap_path(path)
    _reject_symlinked_path(path.parent)
    if not path.name or path.name in {".", ".."}:
        raise ValueError("capture-mode receipt path must name one file")
    parent = Path(os.path.abspath(path.parent))
    _reject_qnap_path(parent)
    try:
        parent_mode = os.lstat(parent).st_mode
    except FileNotFoundError as error:
        raise ValueError("capture-mode receipt parent does not exist") from error
    if not stat.S_ISDIR(parent_mode):
        raise ValueError("capture-mode receipt parent is not a directory")
    destination = parent / path.name
    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError(f"immutable capture-mode receipt already exists: {destination}")
    payload = receipt.model_dump_json(indent=2).encode("utf-8") + b"\n"
    if len(payload) > 128 * 1024:
        raise ValueError("capture-mode receipt exceeds its bounded size")
    temporary = parent / f".{path.name}.{os.getpid()}-{uuid4().hex}.partial"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o440,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination, follow_symlinks=False)
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _reject_qnap_path(path: Path) -> None:
    absolute = Path(os.path.abspath(path))
    qnap = Path("/mnt/qnap01")
    if absolute == qnap or qnap in absolute.parents:
        raise ValueError("capture-mode acceptance cannot use a QNAP path")


def _reject_symlinked_path(path: Path) -> None:
    """Reject every existing symlink component without following its target."""

    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return
        if stat.S_ISLNK(mode):
            target = Path(os.readlink(current))
            lexical_target = target if target.is_absolute() else current.parent / target
            _reject_qnap_path(lexical_target)
            raise ValueError(f"capture-mode acceptance path is symlinked: {current}")
