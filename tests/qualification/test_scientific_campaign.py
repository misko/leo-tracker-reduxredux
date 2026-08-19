from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

from leo.contracts import (
    CalibrationEvidenceV1,
    NativeExecutionReceiptV2,
    NativeKnownPilotEvidenceProductV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
    TrustedNativeReleaseEvidenceV2,
    canonical_digest,
)
from leo.contracts.scientific import DetectorPipelineBindingV1
from leo.domain.profiles import load_profile_revision
from leo.qualification.capture_modes import (
    CaptureModeAcceptanceHarness,
    CaptureModeExpectationV1,
)
from leo.qualification.scientific_campaign import (
    ProductBackedMatchedAcceptanceBindingProvider,
    campaign_config_from_accepted_capture,
)
from leo.storage import RecordingStore

_CAPTURE_TEST_HELPERS = run_path(str(Path(__file__).with_name("test_capture_modes.py")))
_HARDWARE_IDS = _CAPTURE_TEST_HELPERS["_HARDWARE_IDS"]
_synthetic_hardware_check = _CAPTURE_TEST_HELPERS["_synthetic_hardware_check"]
_LEGACY_TEST_HELPERS = run_path(str(Path(__file__).with_name("test_legacy_oracle.py")))
_legacy_receipt = _LEGACY_TEST_HELPERS["_receipt"]


def _binding() -> DetectorPipelineBindingV1:
    return DetectorPipelineBindingV1.create(
        native_source_revision="native-review-1",
        native_source_tree_digest="sha256:" + "7" * 64,
        native_release_manifest_digest="sha256:" + "8" * 64,
        native_template_digest="sha256:" + "4" * 64,
        native_acquisition_configuration_digest="sha256:" + "5" * 64,
        native_qam_configuration_digest="sha256:" + "6" * 64,
        pipeline_release="review-release",
    )


def test_accepted_capture_receipt_derives_exact_science_inventory(
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
    receipt = CaptureModeAcceptanceHarness(RecordingStore(tmp_path / "bulk")).run_campaign(
        expectation,
        acceptance_id="accepted-capture-campaign",
        independent_radio_a_session_ids=tuple(f"a-{index}" for index in range(10)),
        independent_radio_b_session_ids=tuple(f"b-{index}" for index in range(10)),
        synchronized_pair_session_ids=tuple(f"pair-{index}" for index in range(10)),
        observed_utc_ns=1_800_000_100_000_000_000,
    )

    config = campaign_config_from_accepted_capture(
        campaign_id="science-campaign",
        capture_receipt=receipt,
        detector_binding=_binding(),
    )
    assert len(config.capture_inventory) == 40
    assert len({item.session_id for item in config.capture_inventory}) == 30
    assert {item.receiver_id for item in config.capture_inventory} == {1}
    assert len({item.profile_revision_digest for item in config.capture_inventory}) == 1

    pair = receipt.trial_receipts[0].checks[2].model_copy(update={"overlap_fraction": 0.5})
    trial = receipt.trial_receipts[0].model_copy(
        update={"checks": (*receipt.trial_receipts[0].checks[:2], pair)}
    )
    forged = receipt.model_copy(update={"trial_receipts": (trial, *receipt.trial_receipts[1:])})
    with pytest.raises(ValueError, match="estimated overlap"):
        campaign_config_from_accepted_capture(
            campaign_id="forged-science-campaign",
            capture_receipt=forged,
            detector_binding=_binding(),
        )


def test_product_backed_binding_is_exact_scope_and_rejects_forged_product(
    tmp_path: Path,
) -> None:
    binding = DetectorPipelineBindingV1.create(
        native_source_revision="a" * 40,
        native_source_tree_digest="sha256:" + "7" * 64,
        native_release_manifest_digest="sha256:" + "8" * 64,
        native_template_digest="sha256:" + "4" * 64,
        native_acquisition_configuration_digest="sha256:" + "5" * 64,
        native_qam_configuration_digest="sha256:" + "6" * 64,
        pipeline_release="review-release",
    )
    path = ReceiverPathIdentityV1(
        radio_id="radio-a",
        radio_serial="serial-a",
        receiver_id=1,
        physical_receiver_id="radio-a-rx1",
        capture_utc_ns=1_000,
        capture_end_utc_ns=60_000_001_000,
        hardware_epoch_id="epoch-a",
        session_id="session-a",
        stream_id="stream-a",
        manifest_digest="sha256:" + "3" * 64,
        profile_revision_digest="sha256:" + "9" * 64,
    )
    calibration = ReceiverFrequencyCalibrationV1.create(
        calibration_id="cal-a",
        radio_id=path.radio_id,
        radio_serial=path.radio_serial,
        receiver_id=1,
        physical_receiver_id=path.physical_receiver_id,
        hardware_epoch_id=path.hardware_epoch_id,
        center_hz=-162_048.5,
        uncertainty_lower_hz=-162_050.0,
        uncertainty_upper_hz=-162_047.0,
        valid_from_utc_ns=0,
        valid_until_utc_ns=100_000_000_000,
        method="fixture",
        created_utc_ns=0,
        evidence=(
            CalibrationEvidenceV1(
                kind="fixture",
                uri="fixture://cal-a",
                digest="sha256:" + "2" * 64,
            ),
        ),
    )
    decisions = tuple(
        PilotWindowDecisionV1.create(
            source="native",
            algorithm_id="native-symbolwise-known-pilot",
            algorithm_version="1.0.0",
            window_iq_digest=f"sha256:{index:064x}",
            window_index=index,
            sample_start=index * 250_000,
            status=PilotDecisionStatus.EVALUATED,
            candidate=False,
            reason="sealed fixture negative",
        )
        for index in range(600)
    )
    execution = NativeExecutionReceiptV2.create(
        pipeline_release=binding.pipeline_release,
        source_revision=binding.native_source_revision,
        source_tree_digest=binding.native_source_tree_digest,
        release_manifest_digest=binding.native_release_manifest_digest,
        template_digest=binding.native_template_digest,
        acquisition_configuration_digest=binding.native_acquisition_configuration_digest,
        qam_configuration_digest=binding.native_qam_configuration_digest,
        worker_digest="sha256:" + "c" * 64,
        interpreter_digest="sha256:" + "d" * 64,
        runtime_package_tree_digest="sha256:" + "e" * 64,
        execution_environment_digest="sha256:" + "f" * 64,
        worker_output_digest="sha256:" + "0" * 64,
        input_manifest_digest=path.manifest_digest,
        session_id=path.session_id,
        stream_id=path.stream_id,
        calibration_digest=calibration.calibration_digest,
        decisions=decisions,
    )
    release_values = {
        "schema_version": 2,
        "kind": "validated-current-native-release",
        "pipeline_release": binding.pipeline_release,
        "source_revision": binding.native_source_revision,
        "git_tree": "b" * 40,
        "source_tree_digest": binding.native_source_tree_digest,
        "release_metadata_digest": binding.native_release_manifest_digest,
        "worker_digest": "sha256:" + "c" * 64,
        "interpreter_digest": "sha256:" + "d" * 64,
        "runtime_package_tree_digest": "sha256:" + "e" * 64,
        "release_path": "/opt/leo-tracker/releases/" + "a" * 40,
        "validator": "deployed-release-validators-v1",
    }
    release = TrustedNativeReleaseEvidenceV2(
        **release_values,
        evidence_digest=canonical_digest(release_values),
    )

    def evidence_product(scope_key: str) -> NativeKnownPilotEvidenceProductV2:
        values = {
            "schema_version": 2,
            "kind": "native-known-pilot-evidence",
            "analysis_run_id": "run-a",
            "scope_key": scope_key,
            "release": release.model_dump(mode="json"),
            "path_identity": path.model_dump(mode="json"),
            "calibration": calibration.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json"),
            "acceptance_eligible": False,
        }
        return NativeKnownPilotEvidenceProductV2(
            analysis_run_id="run-a",
            scope_key=scope_key,
            release=release,
            path_identity=path,
            calibration=calibration,
            execution=execution,
            product_digest=canonical_digest(values),
        )

    class Scopes:
        def resolve(self, _context, _iq):
            return path.manifest_digest, path, calibration

    class Legacy:
        def resolve(self, _context, _path):
            return _legacy_receipt(tmp_path)

    class Products:
        def __init__(self, product):
            self.product = product

        def read_json(self, requirement):
            assert requirement.accepted_schema_versions == (2,)
            return self.product.model_dump(mode="json")

    class Iq:
        sample_rate_hz = 2_500_000
        center_frequency_hz = 1_709_521_250
        sample_count = 150_000_000
        receiver_ids = (1,)

        def iter_blocks(self, *, block_samples):
            del block_samples
            return ()

    from leo.pipeline import AnalysisContext

    provider = ProductBackedMatchedAcceptanceBindingProvider(
        detector_binding=binding,
        scopes=Scopes(),
        legacy=Legacy(),
    )
    context = AnalysisContext(
        session_id="session-a",
        run_id="run-a",
        pipeline_release="review-release",
        scope_key="stream-a",
    )
    resolved = provider.resolve(context, Iq(), Products(evidence_product("stream-a")))
    assert resolved.path_identity == path
    assert resolved.legacy_execution is not None
    assert resolved.native_execution is None

    with pytest.raises(ValueError, match="same-scope"):
        provider.resolve(context, Iq(), Products(evidence_product("other-stream")))
