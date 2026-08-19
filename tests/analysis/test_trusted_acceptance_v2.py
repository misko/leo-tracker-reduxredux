from __future__ import annotations

from pathlib import Path
from runpy import run_path
from typing import Literal

import pytest
from pydantic import ValidationError

from leo.analysis.starlink.trusted_acceptance import (
    evaluate_trusted_campaign_v2,
    evaluate_trusted_matched_recovery_v2,
)
from leo.contracts.calibration import (
    CalibrationEvidenceV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.scientific import (
    DetectorPipelineBindingV1,
    LegacyExecutionEnvelopeV1,
    MatchedAcceptanceStatus,
    MatchedPilotAcceptanceConfigV1,
    NativeExecutionReceiptV2,
    NativeKnownPilotEvidenceProductV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    TrustedNativeReleaseEvidenceV2,
)
from leo.contracts.trusted_scientific import TrustedMatchedRecoveryReceiptV2
from leo.domain.profiles import load_profile_revision
from leo.qualification.capture_modes import (
    CaptureModeAcceptanceHarness,
    CaptureModeExpectationV1,
)
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.storage import RecordingStore

_CAPTURE_HELPERS = run_path(
    str(Path(__file__).parents[1] / "qualification" / "test_capture_modes.py")
)
_HARDWARE_IDS = _CAPTURE_HELPERS["_HARDWARE_IDS"]
_synthetic_hardware_check = _CAPTURE_HELPERS["_synthetic_hardware_check"]

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def _binding(*, release: str = "trusted-release") -> DetectorPipelineBindingV1:
    return DetectorPipelineBindingV1.create(
        native_source_revision="1" * 40,
        native_source_tree_digest="sha256:" + "2" * 64,
        native_release_manifest_digest="sha256:" + "3" * 64,
        native_template_digest="sha256:" + "4" * 64,
        native_acquisition_configuration_digest="sha256:" + "5" * 64,
        native_qam_configuration_digest="sha256:" + "6" * 64,
        pipeline_release=release,
    )


def _identity(
    *,
    session_id: str = "session-a",
    stream_id: str = "stream-a",
    manifest_digest: str = DIGEST_A,
    profile_digest: str = DIGEST_B,
    radio_id: str = "radio-a",
    radio_serial: str = "serial-a",
    physical_receiver_id: str = "radio-a-rx1",
    hardware_epoch_id: str = "epoch-a",
    start_ns: int = 1_800_000_000_000_000_000,
    end_ns: int = 1_800_000_060_000_000_000,
) -> ReceiverPathIdentityV1:
    return ReceiverPathIdentityV1(
        radio_id=radio_id,
        radio_serial=radio_serial,
        receiver_id=1,
        physical_receiver_id=physical_receiver_id,
        capture_utc_ns=start_ns,
        capture_end_utc_ns=end_ns,
        hardware_epoch_id=hardware_epoch_id,
        session_id=session_id,
        stream_id=stream_id,
        manifest_digest=manifest_digest,
        profile_revision_digest=profile_digest,
    )


def _calibration(identity: ReceiverPathIdentityV1) -> ReceiverFrequencyCalibrationV1:
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=f"cal-{identity.session_id}-{identity.stream_id}",
        radio_id=identity.radio_id,
        radio_serial=identity.radio_serial,
        receiver_id=identity.receiver_id,
        physical_receiver_id=identity.physical_receiver_id,
        hardware_epoch_id=identity.hardware_epoch_id,
        center_hz=0.0,
        uncertainty_lower_hz=-10.0,
        uncertainty_upper_hz=10.0,
        valid_from_utc_ns=identity.capture_utc_ns,
        valid_until_utc_ns=identity.capture_end_utc_ns,
        method="trusted-fixture",
        created_utc_ns=identity.capture_utc_ns - 1,
        evidence=(
            CalibrationEvidenceV1(
                kind="trusted-fixture",
                uri=f"fixture://{identity.session_id}/{identity.stream_id}/calibration",
                digest=DIGEST_B,
            ),
        ),
    )


def _decisions(
    source: str,
    *,
    missing_index: int | None = None,
    changed_digest_index: int | None = None,
) -> tuple[PilotWindowDecisionV1, ...]:
    values: list[PilotWindowDecisionV1] = []
    for index in range(600):
        normalized_source: Literal["legacy_reference", "native"] = (
            "legacy_reference" if source == "legacy_reference" else "native"
        )
        if index == missing_index:
            values.append(
                PilotWindowDecisionV1.create(
                    source=normalized_source,
                    algorithm_id="unavailable-window-decision",
                    algorithm_version="1.0.0",
                    window_iq_digest=None,
                    window_index=index,
                    sample_start=index * 250_000,
                    status=PilotDecisionStatus.INSUFFICIENT,
                    candidate=None,
                    reason="sealed worker reported a missing window",
                )
            )
            continue
        digest_index = index + 1_000 if index == changed_digest_index else index
        values.append(
            PilotWindowDecisionV1.create(
                source=normalized_source,
                algorithm_id=(
                    "leo-tracker-pilot-symbolwise-v3-single-rx"
                    if source == "legacy_reference"
                    else "native-symbolwise-known-pilot"
                ),
                algorithm_version=(
                    "0bb80d14759fd8496b74e7d3219a690be18565a6"
                    if source == "legacy_reference"
                    else "1.0.0"
                ),
                window_iq_digest=f"sha256:{digest_index:064x}",
                window_index=index,
                sample_start=index * 250_000,
                status=PilotDecisionStatus.EVALUATED,
                candidate=True,
                epoch_sample=100,
                cfo_hz=1000.0,
                qam_accuracy=0.9,
                qam_evm=0.5,
                reason="sealed candidate-only trusted fixture",
            )
        )
    return tuple(values)


def _legacy(
    identity: ReceiverPathIdentityV1,
    calibration: ReceiverFrequencyCalibrationV1,
    decisions: tuple[PilotWindowDecisionV1, ...],
    binding: DetectorPipelineBindingV1,
) -> LegacyExecutionEnvelopeV1:
    values = {
        "schema_version": 1,
        "kind": "loaded-sealed-legacy-pilot-oracle",
        "oracle_receipt_digest": DIGEST_A,
        "oracle_configuration_digest": DIGEST_B,
        "oracle_environment_digest": binding.legacy_environment_digest,
        "oracle_worker_output_digest": "sha256:" + "7" * 64,
        "oracle_iq_digest": "sha256:" + "8" * 64,
        "receiver_center_hz": calibration.center_hz,
        "input_manifest_digest": identity.manifest_digest,
        "session_id": identity.session_id,
        "stream_id": identity.stream_id,
        "calibration_digest": calibration.calibration_digest,
        "decisions": tuple(item.model_dump(mode="json") for item in decisions),
    }
    return LegacyExecutionEnvelopeV1.model_validate(
        {**values, "envelope_digest": canonical_digest(values)}
    )


def _native(
    identity: ReceiverPathIdentityV1,
    calibration: ReceiverFrequencyCalibrationV1,
    decisions: tuple[PilotWindowDecisionV1, ...],
    binding: DetectorPipelineBindingV1,
    *,
    run_id: str,
) -> NativeKnownPilotEvidenceProductV2:
    release_values = {
        "schema_version": 2,
        "kind": "validated-current-native-release",
        "pipeline_release": binding.pipeline_release,
        "source_revision": binding.native_source_revision,
        "git_tree": "9" * 40,
        "source_tree_digest": binding.native_source_tree_digest,
        "release_metadata_digest": binding.native_release_manifest_digest,
        "worker_digest": "sha256:" + "c" * 64,
        "interpreter_digest": "sha256:" + "d" * 64,
        "runtime_package_tree_digest": "sha256:" + "e" * 64,
        "release_path": "/opt/leo-tracker/releases/" + "9" * 40,
        "validator": "deployed-release-validators-v1",
    }
    release = TrustedNativeReleaseEvidenceV2.model_validate(
        {**release_values, "evidence_digest": canonical_digest(release_values)}
    )
    execution = NativeExecutionReceiptV2.create(
        pipeline_release=binding.pipeline_release,
        source_revision=binding.native_source_revision,
        source_tree_digest=binding.native_source_tree_digest,
        release_manifest_digest=binding.native_release_manifest_digest,
        template_digest=binding.native_template_digest,
        acquisition_configuration_digest=binding.native_acquisition_configuration_digest,
        qam_configuration_digest=binding.native_qam_configuration_digest,
        worker_digest=release.worker_digest,
        interpreter_digest=release.interpreter_digest,
        runtime_package_tree_digest=release.runtime_package_tree_digest,
        execution_environment_digest="sha256:" + "f" * 64,
        worker_output_digest="sha256:" + "0" * 64,
        input_manifest_digest=identity.manifest_digest,
        session_id=identity.session_id,
        stream_id=identity.stream_id,
        calibration_digest=calibration.calibration_digest,
        decisions=decisions,
    )
    values = {
        "schema_version": 2,
        "kind": "native-known-pilot-evidence",
        "analysis_run_id": run_id,
        "scope_key": identity.stream_id,
        "release": release.model_dump(mode="json"),
        "path_identity": identity.model_dump(mode="json"),
        "calibration": calibration.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json"),
        "acceptance_eligible": False,
    }
    return NativeKnownPilotEvidenceProductV2.model_validate(
        {**values, "product_digest": canonical_digest(values)}
    )


def _product(
    identity: ReceiverPathIdentityV1,
    *,
    binding: DetectorPipelineBindingV1 | None = None,
    missing_index: int | None = None,
    changed_digest_index: int | None = None,
):
    binding = binding or _binding()
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=binding)
    calibration = _calibration(identity)
    legacy = _legacy(identity, calibration, _decisions("legacy_reference"), binding)
    native = _native(
        identity,
        calibration,
        _decisions(
            "native",
            missing_index=missing_index,
            changed_digest_index=changed_digest_index,
        ),
        binding,
        run_id=f"run-{identity.session_id}",
    )
    return evaluate_trusted_matched_recovery_v2(
        analysis_run_id=native.analysis_run_id,
        config=config,
        path_identity=identity,
        calibration=calibration,
        legacy_execution=legacy,
        native_evidence=native,
    )


def test_trusted_recovery_replays_all_windows_and_statistics() -> None:
    product = _product(_identity())
    receipt = product.receipt
    assert receipt.content_complete
    assert receipt.mathematical_eligible
    assert not receipt.acceptance_eligible
    assert not receipt.production_accepted
    assert receipt.status is MatchedAcceptanceStatus.PASS
    assert receipt.complete_raw_window_count == 600
    assert receipt.recovery.successes == receipt.recovery.trials == 600
    document = receipt.model_dump(mode="json")
    assert not ({"artifact_id", "analysis_product_uri", "catalog_artifact_uri"} & document.keys())

    forged = receipt.model_dump(mode="python")
    forged["counts"]["n11"] = 599
    forged["counts"]["n10"] = 1
    with pytest.raises(ValidationError, match="independently replayed"):
        TrustedMatchedRecoveryReceiptV2.model_validate(forged)


def test_trusted_recovery_rejects_iq_forgery_and_scope_retarget() -> None:
    identity = _identity()
    with pytest.raises(ValidationError, match="same normalized IQ"):
        _product(identity, changed_digest_index=17)

    other = _identity(stream_id="stream-retargeted")
    calibration = _calibration(other)
    binding = _binding()
    native = _native(
        other,
        calibration,
        _decisions("native"),
        binding,
        run_id="run-retargeted",
    )
    original_calibration = _calibration(identity)
    with pytest.raises(ValidationError, match="same-IQ scope"):
        evaluate_trusted_matched_recovery_v2(
            analysis_run_id=native.analysis_run_id,
            config=MatchedPilotAcceptanceConfigV1.create(detector_binding=binding),
            path_identity=identity,
            calibration=original_calibration,
            legacy_execution=_legacy(
                identity,
                original_calibration,
                _decisions("legacy_reference"),
                binding,
            ),
            native_evidence=native,
        )


def test_missing_native_window_is_retained_but_never_verified_or_eligible() -> None:
    receipt = _product(_identity(), missing_index=11).receipt
    assert receipt.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert receipt.missing_or_insufficient_window_count == 1
    assert not receipt.content_complete
    assert not receipt.mathematical_eligible
    assert not receipt.acceptance_eligible
    assert len(receipt.windows) == 600


def test_campaign_v2_replays_exact_inventory_and_rejects_mixed_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = load_profile_revision(
        Path(__file__).parents[2] / "profiles" / "starlink-ch4-lower-2p5m-60s-rx1-centered-v1.yaml"
    )
    expectation = CaptureModeExpectationV1.from_hardware_profile_revision(
        revision,
        _HARDWARE_IDS,
    )

    def passed_check(self, expected, role, session_id, expected_radios):
        del self
        return _synthetic_hardware_check(expected, role, session_id, expected_radios)

    monkeypatch.setattr(CaptureModeAcceptanceHarness, "_check", passed_check)
    capture = CaptureModeAcceptanceHarness(RecordingStore(tmp_path / "bulk")).run_campaign(
        expectation,
        acceptance_id="trusted-capture",
        independent_radio_a_session_ids=tuple(f"a-{index}" for index in range(10)),
        independent_radio_b_session_ids=tuple(f"b-{index}" for index in range(10)),
        synchronized_pair_session_ids=tuple(f"pair-{index}" for index in range(10)),
        observed_utc_ns=1_800_000_100_000_000_000,
    )
    binding = _binding()
    config = campaign_config_from_accepted_capture(
        campaign_id="trusted-science",
        capture_receipt=capture,
        detector_binding=binding,
    )
    products = tuple(
        _product(
            _identity(
                session_id=item.session_id,
                stream_id=item.stream_id,
                manifest_digest=item.manifest_digest,
                profile_digest=item.profile_revision_digest,
                radio_id=item.radio_id,
                radio_serial=item.radio_serial,
                physical_receiver_id=item.physical_receiver_id,
                hardware_epoch_id=item.hardware_epoch_id,
                start_ns=item.dwell_start_utc_ns,
                end_ns=item.dwell_end_utc_ns,
            ),
            binding=binding,
        )
        for item in config.capture_inventory
    )
    campaign = evaluate_trusted_campaign_v2(config=config, products=products)
    assert campaign.content_complete and campaign.mathematical_eligible
    assert not campaign.acceptance_eligible and not campaign.production_accepted
    assert campaign.status is MatchedAcceptanceStatus.PASS
    assert len(campaign.streams) == 40
    assert len(campaign.strata) == 4

    mixed = _product(
        products[0].receipt.path_identity,
        binding=_binding(release="other-release"),
    )
    with pytest.raises(ValidationError, match="mixed-release"):
        evaluate_trusted_campaign_v2(config=config, products=(mixed, *products[1:]))
