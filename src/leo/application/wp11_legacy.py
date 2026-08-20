"""Campaign-bound production adapter for frozen legacy-oracle receipts."""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

from leo.analysis.starlink import SymbolwiseAcquisitionConfig
from leo.analysis.starlink.acceptance import (
    native_acquisition_configuration_digest,
    native_qam_configuration_digest,
    native_template_digest,
)
from leo.application.frequency_calibration import NativeReleaseCalibrationEvidenceAdapter
from leo.application.trusted_campaign import ImmutableCaptureCampaignAuthority
from leo.application.trusted_matched_recovery import PostgresAuthoritativeCalibrationScope
from leo.application.wp11_operations import (
    WP11CampaignPlanV1,
    WP11PlanMemberV1,
    validate_authoritative_plan,
)
from leo.contracts.digests import canonical_json_bytes
from leo.contracts.scientific import DetectorPipelineBindingV1, MatchedPilotAcceptanceConfigV1
from leo.contracts.states import StarlinkEdge
from leo.qualification.legacy_oracle import (
    LegacyOracleReceiptV1,
    load_sealed_legacy_receipt_pinned,
    run_legacy_oracle_fd,
)
from leo.qualification.wp11_plan_store import ImmutableWP11PlanStore
from leo.storage import PinnedLocalRoot, RecordingIqReader, RecordingStore


@dataclass(frozen=True, slots=True)
class WP11LegacyReceiptStatus:
    ordinal: int
    session_id: str
    stream_id: str
    receipt_name: str
    receipt_digest: str
    state: Literal["created", "existing"]


@dataclass(frozen=True, slots=True)
class WP11LegacyRunResult:
    campaign_id: str
    requested_count: int
    created_count: int
    existing_count: int
    receipts: tuple[WP11LegacyReceiptStatus, ...]


@dataclass(frozen=True, slots=True)
class WP11ConfigPublication:
    output_path: str
    config_digest: str
    state: Literal["created", "existing"]


def publish_current_wp11_config(
    releases: NativeReleaseCalibrationEvidenceAdapter,
    output_path: Path,
) -> WP11ConfigPublication:
    """Create-only publication of the config derived from the deployed release."""

    if type(releases) is not NativeReleaseCalibrationEvidenceAdapter:
        raise TypeError("WP11 config publication requires deployed release authority")
    current = releases.current_release().native_release
    binding = DetectorPipelineBindingV1.create(
        native_source_revision=current.source_revision,
        native_source_tree_digest=current.source_tree_digest,
        native_release_manifest_digest=current.release_metadata_digest,
        native_template_digest=native_template_digest(StarlinkEdge.LOWER),
        native_acquisition_configuration_digest=native_acquisition_configuration_digest(
            SymbolwiseAcquisitionConfig(maximum_probe_samples=25_000)
        ),
        native_qam_configuration_digest=native_qam_configuration_digest(),
        pipeline_release=current.pipeline_release,
    )
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=binding)
    payload = canonical_json_bytes(config.model_dump(mode="json")) + b"\n"
    parent = PinnedLocalRoot(output_path.parent)
    try:
        name = output_path.name
        if not name or name in {".", ".."} or "/" in name:
            raise ValueError("WP11 config output name is unsafe")
        try:
            descriptor = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o440,
                dir_fd=parent.fileno(),
            )
        except FileExistsError:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent.fileno())
            try:
                if os.read(descriptor, len(payload) + 1) != payload:
                    raise FileExistsError("immutable WP11 config output differs")
            finally:
                os.close(descriptor)
            state: Literal["created", "existing"] = "existing"
        else:
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.fsync(parent.fileno())
            state = "created"
    finally:
        parent.close()
    return WP11ConfigPublication(
        output_path=str(output_path),
        config_digest=config.config_digest,
        state=state,
    )


class WP11LegacyOracleCampaignRunner:
    """Materialize verified RecordingStore RX1 IQ into one anonymous spool at a time."""

    def __init__(
        self,
        *,
        plans: ImmutableWP11PlanStore,
        capture: ImmutableCaptureCampaignAuthority,
        scopes: PostgresAuthoritativeCalibrationScope,
        recordings: RecordingStore,
        spool: PinnedLocalRoot,
        evidence_root: PinnedLocalRoot,
        pipeline_release_id: str,
    ) -> None:
        if type(plans) is not ImmutableWP11PlanStore:
            raise TypeError("legacy campaign runner requires the immutable WP11 plan store")
        if type(capture) is not ImmutableCaptureCampaignAuthority:
            raise TypeError("legacy campaign runner requires concrete capture authority")
        if type(scopes) is not PostgresAuthoritativeCalibrationScope:
            raise TypeError("legacy campaign runner requires authoritative calibration scope")
        if type(recordings) is not RecordingStore or recordings.pinned_root_identity is None:
            raise TypeError("legacy campaign runner requires pinned RecordingStore")
        self._plans = plans
        self._capture = capture
        self._scopes = scopes
        self._recordings = recordings
        self._spool = spool.clone()
        self._evidence_root = evidence_root.clone()
        self._pipeline_release_id = pipeline_release_id

    def close(self) -> None:
        self._spool.close()
        self._evidence_root.close()

    def run(
        self,
        campaign_id: str,
        *,
        ordinals: tuple[int, ...] = (),
    ) -> WP11LegacyRunResult:
        plan, _ref = self._plans.load(campaign_id)
        validate_authoritative_plan(
            plan,
            self._capture,
            expected_pipeline_release_id=self._pipeline_release_id,
        )
        selected = ordinals if ordinals else tuple(range(40))
        if len(set(selected)) != len(selected) or any(
            value < 0 or value >= 40 for value in selected
        ):
            raise ValueError("legacy receipt ordinals must be unique integers from 0 through 39")
        statuses = tuple(self._run_member(plan, plan.members[ordinal]) for ordinal in selected)
        return WP11LegacyRunResult(
            campaign_id=campaign_id,
            requested_count=len(selected),
            created_count=sum(item.state == "created" for item in statuses),
            existing_count=sum(item.state == "existing" for item in statuses),
            receipts=statuses,
        )

    def require_complete(self, campaign_id: str) -> None:
        """Fail before job creation unless every immutable campaign receipt exists."""

        plan, _ref = self._plans.load(campaign_id)
        validate_authoritative_plan(
            plan,
            self._capture,
            expected_pipeline_release_id=self._pipeline_release_id,
        )
        for member in plan.members:
            load_sealed_legacy_receipt_pinned(
                evidence_root=self._evidence_root,
                receipt_name=member.legacy_receipt_name,
            )

    def _run_member(
        self,
        plan: WP11CampaignPlanV1,
        member: WP11PlanMemberV1,
    ) -> WP11LegacyReceiptStatus:
        inventory = member.inventory
        scope, reader, bundle_uri = self._scopes.resolve_recording(
            inventory.session_id,
            inventory.stream_id,
        )
        if type(reader) is not RecordingIqReader:
            raise TypeError("legacy campaign IQ did not come from RecordingStore")
        descriptor, digest = self._materialize(reader)
        try:
            try:
                existing = load_sealed_legacy_receipt_pinned(
                    evidence_root=self._evidence_root,
                    receipt_name=member.legacy_receipt_name,
                )
            except FileNotFoundError:
                receipt = run_legacy_oracle_fd(
                    iq_fd=descriptor,
                    iq_label=f"{bundle_uri}#{inventory.stream_id}/rx1",
                    expected_iq_sha256=digest,
                    receiver_center_hz=scope.calibration.center_hz,
                    evidence_root=self._evidence_root,
                    receipt_name=member.legacy_receipt_name,
                )
                state: Literal["created", "existing"] = "created"
            else:
                self._validate_existing(existing, digest, scope.calibration.center_hz)
                receipt = existing
                state = "existing"
        finally:
            os.close(descriptor)
        return WP11LegacyReceiptStatus(
            ordinal=member.ordinal,
            session_id=inventory.session_id,
            stream_id=inventory.stream_id,
            receipt_name=member.legacy_receipt_name,
            receipt_digest=receipt.receipt_digest,
            state=state,
        )

    def _materialize(self, reader: RecordingIqReader) -> tuple[int, str]:
        self._spool.assert_open()
        name = f".wp11-legacy-{os.getpid()}-{secrets.token_hex(8)}.ci16"
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o400,
            dir_fd=self._spool.fileno(),
        )
        digest = hashlib.sha256()
        sample_count = 0
        try:
            receiver_index = reader.receiver_ids.index(1)
            for block in reader.iter_blocks(block_samples=1_000_000):
                if block.metadata.session_sample_start != sample_count:
                    raise ValueError("legacy spool cannot cross an IQ discontinuity")
                selected = np.ascontiguousarray(block.samples[:, receiver_index, :], dtype="<i2")
                payload = selected.tobytes(order="C")
                digest.update(payload)
                _write_all(descriptor, payload)
                sample_count += block.metadata.sample_count
            if sample_count != reader.sample_count:
                raise ValueError("legacy spool does not cover the exact recording dwell")
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            os.unlink(name, dir_fd=self._spool.fileno())
            raise
        os.close(descriptor)
        source = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self._spool.fileno())
        os.unlink(name, dir_fd=self._spool.fileno())
        os.fsync(self._spool.fileno())
        return source, f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _validate_existing(
        receipt: LegacyOracleReceiptV1,
        iq_digest: str,
        receiver_center_hz: float,
    ) -> None:
        if (
            receipt.iq_sha256 != iq_digest
            or receipt.config.receiver_center_hz != receiver_center_hz
        ):
            raise ValueError("existing legacy receipt differs from authoritative IQ/calibration")


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError("legacy spool write made no progress")
        offset += written
