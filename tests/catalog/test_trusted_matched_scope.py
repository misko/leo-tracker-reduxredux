from __future__ import annotations

import math
from pathlib import Path

import pytest

from leo.application.trusted_matched_recovery import (
    PostgresAuthoritativeCalibrationScope,
)
from leo.catalog import JobDefinition
from leo.contracts.calibration import CalibrationEvidenceV1, ReceiverFrequencyCalibrationV1
from leo.pipeline import AnalysisContext
from leo.storage import RecordingStore
from tests.catalog.test_calibration_cli_vertical import _materialize_recording
from tests.catalog.test_calibration_repository import _adapter, _register_path, _register_set

from .conftest import CatalogHarness


class _Iq:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 1_709_521_250
    sample_count = 150_000_000
    receiver_ids = (1,)

    def iter_blocks(self, *, block_samples):
        del block_samples
        return ()


def test_concrete_scope_resolves_manifest_identity_through_authoritative_pg(
    catalog_harness: CatalogHarness,
    tmp_path: Path,
) -> None:
    recordings = RecordingStore(tmp_path / "bulk")
    manifest, manifest_digest, uri = _materialize_recording(
        recordings,
        0,
        offset_hz=0.0,
        acceptance=True,
    )
    repository = catalog_harness.repository
    repository.add_pipeline_release(
        release_id="trusted-v2-release",
        code_revision="1" * 40,
        environment_digest="sha256:" + "2" * 64,
        graph_digest="sha256:" + "3" * 64,
    )
    repository.create_capture_session(
        session_id=manifest.session_id,
        source_type="live",
        state="committed",
        bundle_uri=uri,
        manifest_digest=manifest_digest,
    )
    repository.create_analysis_run(
        run_id="trusted-v2-scope-run",
        session_id=manifest.session_id,
        pipeline_release_id="trusted-v2-release",
        input_manifest_digest=manifest_digest,
        jobs=(
            JobDefinition(
                stage_key="native-known-pilot-evidence",
                scope_key=manifest.streams[0].stream_id,
            ),
        ),
        trigger="reprocess",
        promotion_policy="evidence_only",
    )
    adapter, resolver = _adapter(catalog_harness)
    stream = manifest.streams[0]
    assert stream.timing is not None
    start = stream.timing.first_sample.estimate_utc_ns
    end = stream.timing.last_sample.estimate_utc_ns + math.ceil(1_000_000_000 / 2_500_000)
    from leo.contracts.calibration import ReceiverPathIdentityV1

    identity = ReceiverPathIdentityV1(
        radio_id=stream.radio.radio_id,
        radio_serial=stream.radio.serial,
        receiver_id=1,
        physical_receiver_id="rx_lnb_d",
        capture_utc_ns=start,
        capture_end_utc_ns=end,
        hardware_epoch_id="hw_gauss_r21_science_postreboot_20260816_v1",
        session_id=manifest.session_id,
        stream_id=stream.stream_id,
        manifest_digest=manifest_digest,
        profile_revision_digest=manifest.capture_plan.profile_revision.revision_digest,
    )
    calibration = ReceiverFrequencyCalibrationV1.create(
        calibration_id="trusted-v2-calibration",
        radio_id=identity.radio_id,
        radio_serial=identity.radio_serial,
        receiver_id=1,
        physical_receiver_id=identity.physical_receiver_id,
        hardware_epoch_id=identity.hardware_epoch_id,
        center_hz=0.0,
        uncertainty_lower_hz=-100.0,
        uncertainty_upper_hz=100.0,
        valid_from_utc_ns=start - 1,
        valid_until_utc_ns=end + 1,
        method="trusted-fixture",
        created_utc_ns=start - 2,
        evidence=(
            CalibrationEvidenceV1(
                kind="trusted-fixture",
                uri="fixture://trusted-v2-calibration",
                digest="sha256:" + "4" * 64,
            ),
        ),
    )
    _register_path(adapter, identity, started_utc_ns=start - 10)
    _register_set(adapter, resolver, calibration, set_id="trusted-v2-set")
    scope = PostgresAuthoritativeCalibrationScope(repository, recordings, adapter)
    context = AnalysisContext(
        session_id=manifest.session_id,
        run_id="trusted-v2-scope-run",
        pipeline_release="trusted-v2-release",
        scope_key=stream.stream_id,
    )

    resolved = scope.resolve(context, _Iq())

    assert resolved.path_identity == identity
    assert resolved.calibration == calibration
    assert resolved.input_manifest_digest == manifest_digest
    forged = context.model_copy(update={"pipeline_release": "wrong-release"})
    with pytest.raises(ValueError, match="evidence-only catalog lineage"):
        scope.resolve(forged, _Iq())


def test_concrete_scope_rejects_protocol_fakes() -> None:
    with pytest.raises(TypeError, match="concrete PostgreSQL"):
        PostgresAuthoritativeCalibrationScope(  # type: ignore[arg-type]
            object(),
            object(),
            object(),
        )
