from __future__ import annotations

from pathlib import Path
from runpy import run_path

import pytest

from leo.contracts.scientific import DetectorPipelineBindingV1
from leo.domain.profiles import load_profile_revision
from leo.qualification.capture_modes import (
    CaptureModeAcceptanceHarness,
    CaptureModeExpectationV1,
)
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.storage import RecordingStore

_CAPTURE_TEST_HELPERS = run_path(str(Path(__file__).with_name("test_capture_modes.py")))
_HARDWARE_IDS = _CAPTURE_TEST_HELPERS["_HARDWARE_IDS"]
_synthetic_hardware_check = _CAPTURE_TEST_HELPERS["_synthetic_hardware_check"]


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
