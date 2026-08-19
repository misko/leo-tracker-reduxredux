from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.qam import PilotQamResult, analyze_pilot_qam, combine_receiver_qam
from leo.analysis.starlink import (
    FixturePreflightStatus,
    NumericalStatus,
    ReceiverFrequencyCalibration,
    RequiredFixtureError,
    acquire_symbolwise,
    inspect_corpus,
    preflight_corpus,
)

CORPUS_MANIFEST = Path("corpus/manifest.json").resolve()
LOCAL_ROOT = Path(os.environ.get("LEO_REAL_CORPUS_ROOT", "/srv/bulk/leo/test-corpus"))
RETRO_ID = "retro-positive-68p7"


def test_preflight_fails_for_required_and_keeps_j1_explicitly_unavailable(
    tmp_path: Path,
) -> None:
    report = inspect_corpus(CORPUS_MANIFEST, local_corpus_root=tmp_path)

    assert report.by_id(RETRO_ID).status is FixturePreflightStatus.MISSING
    j1 = report.by_id("j1-calibrated-positive-41p6")
    assert j1.requirement == "UNAVAILABLE_HISTORICAL_EVIDENCE"
    assert j1.status is FixturePreflightStatus.UNAVAILABLE_HISTORICAL_EVIDENCE
    assert "absent" in j1.reason
    with pytest.raises(RequiredFixtureError, match=RETRO_ID):
        report.require_ready()
    with pytest.raises(RequiredFixtureError, match="REQUIRED corpus preflight failed"):
        preflight_corpus(CORPUS_MANIFEST, local_corpus_root=tmp_path)


def test_unavailable_j1_preflight_rejects_legacy_or_positive_claims(tmp_path: Path) -> None:
    document = json.loads(CORPUS_MANIFEST.read_bytes())
    j1_index = next(
        index
        for index, fixture in enumerate(document["fixtures"])
        if fixture["fixture_id"] == "j1-calibrated-positive-41p6"
    )
    declaration = tmp_path / "manifest.json"

    legacy = deepcopy(document)
    legacy["schema"] = "org.leo.test-corpus/v1"
    declaration.write_text(json.dumps(legacy), encoding="utf-8")
    with pytest.raises(ValueError, match="requires corpus schema v2"):
        inspect_corpus(declaration, local_corpus_root=tmp_path / "local")

    for section, key, value in (
        ("availability", "source_present", True),
        ("availability", "execution_eligible", True),
        ("availability", "execution_status", "executed"),
        ("availability", "result_status", "passed"),
        ("availability", "parity_status", "passed"),
        ("availability", "passed", True),
        ("availability", "executed", True),
        ("availability", "calibrated", True),
        ("truth", "target_present", True),
        ("truth", "calibrated_detection", True),
        ("truth", "specificity_claimed", True),
        ("truth", "detection_claimed", True),
        ("truth", "parity_claimed", True),
        ("truth", "payload_decoded", True),
        ("truth", "attribution_claimed", True),
        ("truth", "passed", True),
        ("truth", "executed", True),
        ("truth", "calibrated", True),
    ):
        changed = deepcopy(document)
        changed["fixtures"][j1_index]["metadata"][section][key] = value
        declaration.write_text(json.dumps(changed), encoding="utf-8")
        with pytest.raises(ValueError, match="claims|fields"):
            inspect_corpus(declaration, local_corpus_root=tmp_path / "local")

    missing_unknown_truth = deepcopy(document)
    del missing_unknown_truth["fixtures"][j1_index]["metadata"]["truth"]["target_present"]
    declaration.write_text(json.dumps(missing_unknown_truth), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected truth fields"):
        inspect_corpus(declaration, local_corpus_root=tmp_path / "local")


def test_preflight_fails_closed_for_corrupt_required_artifact(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    fixture_root = corpus_root / "corrupt-required"
    fixture_root.mkdir(parents=True)
    (fixture_root / "recording.ci16").write_bytes(b"changed")
    (fixture_root / "fixture-manifest.json").write_text(
        json.dumps(
            {
                "fixture_id": "corrupt-required",
                "source_type": "TEST",
                "tags": ["TEST"],
                "retention": {"protected": True, "hold": "indefinite"},
            }
        )
    )
    (fixture_root / "retention-hold.json").write_text(
        json.dumps({"fixture_id": "corrupt-required", "protected": True})
    )
    declaration = tmp_path / "manifest.json"
    declaration.write_text(
        json.dumps(
            {
                "schema": "org.leo.test-corpus/v1",
                "policy": {"default_local_root": str(corpus_root)},
                "fixtures": [
                    {
                        "fixture_id": "corrupt-required",
                        "requirement": "REQUIRED",
                        "artifacts": [
                            {
                                "target_relative_path": "recording.ci16",
                                "selected_byte_count": 7,
                                "selected_sha256": "0" * 64,
                            }
                        ],
                    }
                ],
            }
        )
    )

    report = inspect_corpus(declaration)

    assert report.by_id("corrupt-required").status is FixturePreflightStatus.CORRUPT
    with pytest.raises(RequiredFixtureError, match="corrupt-required: corrupt"):
        report.require_ready()


@pytest.mark.real_corpus
def test_protected_retro_search_and_conditioned_qam_match_frozen_oracle() -> None:
    report = preflight_corpus(CORPUS_MANIFEST, local_corpus_root=LOCAL_ROOT)
    assert report.by_id(RETRO_ID).status is FixturePreflightStatus.READY
    assert (
        report.by_id("j1-calibrated-positive-41p6").status
        is FixturePreflightStatus.UNAVAILABLE_HISTORICAL_EVIDENCE
    )

    fixture_manifest = json.loads((LOCAL_ROOT / RETRO_ID / "fixture-manifest.json").read_bytes())
    metadata = fixture_manifest["metadata"]
    fmt = metadata["format"]
    expected = metadata["candidate_expectation"]
    raw = np.memmap(
        LOCAL_ROOT / RETRO_ID / "recording.ci16",
        dtype="<i2",
        mode="r",
        shape=(metadata["selection"]["sample_count"], fmt["receiver_count"], 2),
    )
    receiver_results: list[PilotQamResult] = []
    for receiver in range(2):
        values = raw[:, receiver]
        samples = np.asarray(
            (values[:, 0].astype(np.float32) + 1j * values[:, 1]) / 32768.0,
            dtype=np.complex128,
        )
        acquisition = acquire_symbolwise(
            samples,
            fmt["sample_rate_hz"],
            ReceiverFrequencyCalibration(f"retro-rx{receiver}", 0.0, "4" * 64),
        )
        winner = acquisition.winner
        assert acquisition.status is NumericalStatus.COMPLETE
        assert winner is not None
        assert winner.refined_epoch_sample == expected["receiver_epoch_samples"][receiver]
        assert winner.absolute_cfo_hz == pytest.approx(
            expected["receiver_cfo_hz"][receiver], abs=35.0
        )
        assert winner.verify_minus_control_margin > 0.3

        # QAM parity is conditioned at the historical oracle winner. This is a
        # numerical canary, not a calibrated detection or payload decode.
        qam = analyze_pilot_qam(
            samples,
            fmt["sample_rate_hz"],
            epoch_sample=expected["receiver_epoch_samples"][receiver],
            absolute_cfo_hz=expected["receiver_cfo_hz"][receiver],
        )
        assert qam.metrics is not None
        assert qam.metrics.frame_count == 6
        assert qam.metrics.hard_symbol_accuracy == pytest.approx(
            expected["receiver_hard_symbol_accuracy"][receiver], abs=1 / 2400
        )
        expected_evm = (0.9425485730171204, 0.7826223373413086)[receiver]
        assert qam.metrics.rms_evm == pytest.approx(expected_evm, abs=2e-6)
        assert qam.candidate_only is True and qam.known_symbols_only is True
        receiver_results.append(qam)

    combined = combine_receiver_qam(tuple(receiver_results))
    assert combined.metrics is not None
    assert combined.metrics.hard_symbol_accuracy == pytest.approx(
        expected["historical_combined_hard_symbol_accuracy"], abs=1 / 2400
    )
    assert combined.metrics.rms_evm == pytest.approx(0.6380024919780618, abs=2e-6)
