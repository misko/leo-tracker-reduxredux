from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from runpy import run_path

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.starlink import (
    MatchedAcceptanceBinding,
    MatchedPilotAcceptanceAnalyzer,
    NativeEvidenceExecutionResult,
    NativeEvidenceScopeBinding,
    NativeKnownPilotDecisionPort,
    NativeKnownPilotEvidenceAnalyzer,
    StaticMatchedAcceptanceBindingProvider,
    SymbolwiseAcquisitionConfig,
    binomial_lower_bounds,
    calibration_search_domain_covers,
    evaluate_acceptance_campaign,
    evaluate_matched_known_pilot,
    native_acquisition_configuration_digest,
    native_qam_configuration_digest,
    native_template_digest,
    paired_student_t_lower_bound,
)
from leo.contracts import (
    AcceptanceCampaignStreamV1,
    AcceptedCaptureStreamInventoryV1,
    CalibrationEvidenceV1,
    DetectorPipelineBindingV1,
    LegacyExecutionEnvelopeV1,
    MatchedAcceptanceStatus,
    MatchedPilotAcceptanceCampaignConfigV1,
    MatchedPilotAcceptanceConfigV1,
    NativeExecutionReceiptV1,
    NativeKnownPilotEvidenceProductV1,
    NativeKnownPilotEvidenceProductV2,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
    TrustedNativeReleaseEvidenceV2,
    canonical_digest,
    sha256_digest,
)
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.states import StarlinkEdge
from leo.domain.iq import IqBlock
from leo.domain.profiles import load_profile_revision
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    StageOutcome,
)
from leo.qualification.capture_modes import CaptureModeAcceptanceHarness, CaptureModeExpectationV1
from leo.qualification.scientific_campaign import campaign_config_from_accepted_capture
from leo.storage import RecordingStore

_CAPTURE_TEST_HELPERS = run_path(
    str(Path(__file__).parents[1] / "qualification" / "test_capture_modes.py")
)
_HARDWARE_IDS = _CAPTURE_TEST_HELPERS["_HARDWARE_IDS"]
_synthetic_hardware_check = _CAPTURE_TEST_HELPERS["_synthetic_hardware_check"]


def _binding() -> DetectorPipelineBindingV1:
    return DetectorPipelineBindingV1.create(
        native_source_revision="native-commit-456",
        native_source_tree_digest="sha256:" + "1" * 64,
        native_release_manifest_digest="sha256:" + "2" * 64,
        native_template_digest=native_template_digest(StarlinkEdge.LOWER),
        native_acquisition_configuration_digest=native_acquisition_configuration_digest(
            SymbolwiseAcquisitionConfig(maximum_probe_samples=25_000)
        ),
        native_qam_configuration_digest=native_qam_configuration_digest(),
        pipeline_release="test-release",
    )


_BINDING = _binding()


class _ScheduledReader:
    sample_rate_hz = 2_500_000
    center_frequency_hz = 11_325_000_000
    sample_count = 150_000_000
    receiver_ids = (0, 1)

    def __init__(self, *, missing: int | None = None) -> None:
        self.missing = missing
        self.requested: list[int] = []

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        self.requested.append(block_samples)
        assert block_samples >= 25_000
        for index in range(600):
            if index == self.missing:
                continue
            start = index * 250_000
            samples = np.zeros((25_000, 2, 2), dtype="<i2")
            samples[:, 0, 0] = 100
            samples[:, 1, 0] = 200
            interval = NanosecondIntervalV1(lower_ns=start, upper_ns=start)
            yield IqBlock(
                samples=samples,
                metadata=IqBlockMetadataV1(
                    radio_id="radio-a",
                    receiver_ids=(0, 1),
                    sample_count=25_000,
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )


class _DecisionPort:
    maximum_working_set_bytes = 4096

    def __init__(self, source: str, positives: set[int], *, qam: set[int]) -> None:
        self.source = source
        self.positives = positives
        self.qam = qam
        self.observed_mean: float | None = None
        self.detector_binding_digest = _BINDING.binding_digest
        self.oracle_receipt_digest = "sha256:" + "8" * 64
        self.execution_verified = False
        self.native_execution_receipt = None
        self.stream_configuration_digest = "sha256:" + "a" * 64
        self.receiver_center_hz = 125.0

    def evaluate(self, *, window_index, sample_start, samples, sample_rate_hz, calibration):
        del sample_rate_hz, calibration
        self.observed_mean = float(np.real(samples).mean())
        positive = window_index in self.positives
        has_qam = window_index in self.qam
        digest = sha256_digest(np.ascontiguousarray(samples, dtype="<c8").tobytes())
        return PilotWindowDecisionV1.create(
            source=self.source,
            algorithm_id=(
                "leo-tracker-pilot-symbolwise-v3-single-rx"
                if self.source == "legacy_reference"
                else "native-symbolwise-known-pilot"
            ),
            algorithm_version=(
                "0bb80d14759fd8496b74e7d3219a690be18565a6"
                if self.source == "legacy_reference"
                else "1.0.0"
            ),
            window_iq_digest=digest,
            window_index=window_index,
            sample_start=sample_start,
            status=PilotDecisionStatus.EVALUATED,
            candidate=positive,
            epoch_sample=100 if positive else None,
            cfo_hz=10_000.0 if positive else None,
            qam_accuracy=(0.80 if self.source == "legacy_reference" else 0.79) if has_qam else None,
            qam_evm=0.5 if has_qam else None,
            reason="synthetic candidate-only decision",
        )


def _calibration(
    radio: str = "a",
    *,
    valid_until_utc_ns: int = 100_000_000_000,
) -> ReceiverFrequencyCalibrationV1:
    return ReceiverFrequencyCalibrationV1.create(
        calibration_id=f"cal-{radio}",
        radio_id=f"radio-{radio}",
        radio_serial=f"serial-{radio}",
        receiver_id=1,
        physical_receiver_id=f"radio-{radio}-rx1",
        hardware_epoch_id=f"epoch-{radio}-1",
        center_hz=125.0,
        uncertainty_lower_hz=120.0,
        uncertainty_upper_hz=130.0,
        valid_from_utc_ns=0,
        valid_until_utc_ns=valid_until_utc_ns,
        method="reviewed-fixture",
        created_utc_ns=0,
        evidence=(
            CalibrationEvidenceV1(
                kind="fixture",
                uri="fixture://cal-a",
                digest="sha256:" + "2" * 64,
            ),
        ),
    )


def _identity(
    *,
    capture: int = 1_000,
    radio: str = "a",
    session_id: str = "session-a",
    stream_id: str = "stream-a",
    manifest_digest: str = "sha256:" + "e" * 64,
) -> ReceiverPathIdentityV1:
    return ReceiverPathIdentityV1(
        radio_id=f"radio-{radio}",
        radio_serial=f"serial-{radio}",
        receiver_id=1,
        physical_receiver_id=f"radio-{radio}-rx1",
        capture_utc_ns=capture,
        capture_end_utc_ns=capture + 60_000_000_000,
        hardware_epoch_id=f"epoch-{radio}-1",
        session_id=session_id,
        stream_id=stream_id,
        manifest_digest=manifest_digest,
        profile_revision_digest="sha256:" + "f" * 64,
    )


def _evaluate(
    *,
    native_count: int = 100,
    missing: int | None = None,
    calibration=True,
    qam_count: int = 10,
):
    reference = _DecisionPort("legacy_reference", set(range(100)), qam=set(range(qam_count)))
    native = _DecisionPort("native", set(range(native_count)), qam=set(range(qam_count)))
    receipt = evaluate_matched_known_pilot(
        artifact_id="matched-fixture",
        analysis_run_id="run-fixture",
        pipeline_release="test-release",
        production_source_revision="native-commit-456",
        input_manifest_digest="sha256:" + "3" * 64,
        legacy_oracle_receipt_digest="sha256:" + "8" * 64,
        iq=_ScheduledReader(missing=missing),
        path_identity=_identity(manifest_digest="sha256:" + "3" * 64),
        calibration=_calibration() if calibration else None,
        reference=reference,
        native=native,
        config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_BINDING, block_sample_count=25_000
        ),
    )
    return receipt, reference, native


def test_exact_600_window_receipt_counts_and_selects_bound_receiver() -> None:
    receipt, reference, native = _evaluate(native_count=95)

    assert receipt.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert (receipt.counts.n11, receipt.counts.n10, receipt.counts.n01, receipt.counts.n00) == (
        95,
        5,
        0,
        500,
    )
    assert receipt.evaluated_pair_count == 600
    assert receipt.recovery.trials == 100
    assert receipt.recovery.successes == 95
    assert receipt.qam_accuracy_difference_lower_bound == pytest.approx(-0.01)
    assert reference.observed_mean == pytest.approx(200 / 32_768)
    assert native.observed_mean == pytest.approx(200 / 32_768)
    assert receipt.candidate_only is True
    assert receipt.specificity_claimed is False


def test_concrete_native_path_cannot_self_issue_acceptance_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = MatchedPilotAcceptanceConfigV1.create(
        detector_binding=_BINDING,
        block_sample_count=25_000,
    )
    native_fixture = _DecisionPort("native", set(), qam=set())

    def evaluated_negative(self, **kwargs):
        del self
        return native_fixture.evaluate(**kwargs)

    monkeypatch.setattr(NativeKnownPilotDecisionPort, "evaluate", evaluated_negative)
    receipt = evaluate_matched_known_pilot(
        artifact_id="sealed-native",
        analysis_run_id="sealed-native-run",
        pipeline_release="test-release",
        production_source_revision="native-commit-456",
        input_manifest_digest="sha256:" + "3" * 64,
        legacy_oracle_receipt_digest="sha256:" + "8" * 64,
        iq=_ScheduledReader(),
        path_identity=_identity(manifest_digest="sha256:" + "3" * 64),
        calibration=_calibration(),
        reference=_DecisionPort("legacy_reference", set(), qam=set()),
        native=NativeKnownPilotDecisionPort(config, edge=StarlinkEdge.LOWER),
        config=config,
    )

    assert receipt.execution_evidence_verified is False
    assert receipt.legacy_execution_verified is False
    assert receipt.native_execution is None


def test_complete_execution_documents_are_cross_checked_but_v1_remains_nonaccepting() -> None:
    baseline, _, _ = _evaluate()
    calibration = _calibration()
    identity = _identity(manifest_digest="sha256:" + "3" * 64)
    legacy_values = {
        "schema_version": 1,
        "kind": "loaded-sealed-legacy-pilot-oracle",
        "oracle_receipt_digest": "sha256:" + "8" * 64,
        "oracle_configuration_digest": "sha256:" + "a" * 64,
        "oracle_environment_digest": "sha256:" + "b" * 64,
        "oracle_worker_output_digest": "sha256:" + "c" * 64,
        "oracle_iq_digest": "sha256:" + "d" * 64,
        "receiver_center_hz": 125.0,
        "input_manifest_digest": identity.manifest_digest,
        "session_id": identity.session_id,
        "stream_id": identity.stream_id,
        "calibration_digest": calibration.calibration_digest,
        "decisions": tuple(window.reference.model_dump(mode="json") for window in baseline.windows),
    }
    legacy = LegacyExecutionEnvelopeV1(
        **legacy_values,
        envelope_digest=canonical_digest(legacy_values),
    )
    native = NativeExecutionReceiptV1.create(
        pipeline_release=_BINDING.pipeline_release,
        source_revision=_BINDING.native_source_revision,
        source_tree_digest=_BINDING.native_source_tree_digest,
        release_manifest_digest=_BINDING.native_release_manifest_digest,
        template_digest=_BINDING.native_template_digest,
        acquisition_configuration_digest=_BINDING.native_acquisition_configuration_digest,
        qam_configuration_digest=_BINDING.native_qam_configuration_digest,
        input_manifest_digest=identity.manifest_digest,
        session_id=identity.session_id,
        stream_id=identity.stream_id,
        calibration_digest=calibration.calibration_digest,
        decisions=tuple(window.native for window in baseline.windows),
    )
    receipt = evaluate_matched_known_pilot(
        artifact_id="complete-untrusted-evidence",
        analysis_run_id="complete-untrusted-run",
        pipeline_release="test-release",
        production_source_revision="native-commit-456",
        input_manifest_digest=identity.manifest_digest,
        legacy_oracle_receipt_digest=legacy.oracle_receipt_digest,
        iq=_ScheduledReader(),
        path_identity=identity,
        calibration=calibration,
        reference=_DecisionPort("legacy_reference", set(range(100)), qam=set(range(10))),
        native=_DecisionPort("native", set(range(100)), qam=set(range(10))),
        legacy_execution=legacy,
        native_execution=native,
        config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_BINDING,
            block_sample_count=25_000,
        ),
    )
    assert receipt.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert receipt.execution_evidence_verified is False

    changed = receipt.windows[0].reference.model_copy(update={"reason": "forged reason"})
    changed_values = changed.model_dump(mode="python", exclude={"evidence_digest"})
    changed = changed.model_copy(update={"evidence_digest": canonical_digest(changed_values)})
    forged_legacy_values = legacy.model_dump(mode="python", exclude={"envelope_digest"})
    forged_legacy_values["decisions"] = (changed, *legacy.decisions[1:])
    forged_legacy = LegacyExecutionEnvelopeV1(
        **forged_legacy_values,
        envelope_digest=canonical_digest(
            {
                **forged_legacy_values,
                "decisions": tuple(
                    item.model_dump(mode="json") for item in forged_legacy_values["decisions"]
                ),
            }
        ),
    )
    document = receipt.model_dump(mode="python")
    document["legacy_execution"] = forged_legacy
    with pytest.raises(ValidationError, match="not bound to matched windows"):
        type(receipt).model_validate(document)

    forged_native_decision = PilotWindowDecisionV1.create(
        source="native",
        algorithm_id="native-symbolwise-known-pilot",
        algorithm_version="1.0.0",
        window_iq_digest=receipt.windows[0].native.window_iq_digest,
        window_index=0,
        sample_start=0,
        status=PilotDecisionStatus.EVALUATED,
        candidate=False,
        reason="different sealed native decision",
    )
    forged_native = NativeExecutionReceiptV1.create(
        pipeline_release=native.pipeline_release,
        source_revision=native.source_revision,
        source_tree_digest=native.source_tree_digest,
        release_manifest_digest=native.release_manifest_digest,
        template_digest=native.template_digest,
        acquisition_configuration_digest=native.acquisition_configuration_digest,
        qam_configuration_digest=native.qam_configuration_digest,
        input_manifest_digest=native.input_manifest_digest,
        session_id=native.session_id,
        stream_id=native.stream_id,
        calibration_digest=native.calibration_digest,
        decisions=(forged_native_decision, *native.decisions[1:]),
    )
    document = receipt.model_dump(mode="python")
    document["native_execution"] = forged_native
    with pytest.raises(ValidationError, match="differs from matched windows"):
        type(receipt).model_validate(document)


def test_missing_window_or_calibration_fails_closed_without_truncating_denominator() -> None:
    missing, _, _ = _evaluate(missing=17)
    absent, _, _ = _evaluate(calibration=False)

    assert missing.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert len(missing.windows) == 600
    assert missing.missing_or_insufficient_window_count == 1
    assert absent.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert len(absent.windows) == 600
    assert absent.evaluated_pair_count == 0

    expired_calibration = _calibration(valid_until_utc_ns=60_000_000_000)
    reference = _DecisionPort("legacy_reference", set(), qam=set())
    native = _DecisionPort("native", set(), qam=set())
    expired = evaluate_matched_known_pilot(
        artifact_id="expired-calibration",
        analysis_run_id="run-expired",
        pipeline_release="test-release",
        production_source_revision="native-commit-456",
        input_manifest_digest="sha256:" + "3" * 64,
        legacy_oracle_receipt_digest="sha256:" + "8" * 64,
        iq=_ScheduledReader(),
        path_identity=_identity(manifest_digest="sha256:" + "3" * 64),
        calibration=expired_calibration,
        reference=reference,
        native=native,
        config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_BINDING, block_sample_count=25_000
        ),
    )
    assert expired.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert expired.calibration == expired_calibration


def test_candidate_recovery_gate_can_fail_and_low_reference_count_is_inconclusive() -> None:
    failed, _, _ = _evaluate(native_count=70)
    assert failed.status is MatchedAcceptanceStatus.INSUFFICIENT

    reader = _ScheduledReader()
    sparse = _DecisionPort("legacy_reference", set(range(20)), qam=set(range(10)))
    native = _DecisionPort("native", set(range(20)), qam=set(range(10)))
    receipt = evaluate_matched_known_pilot(
        artifact_id="matched-sparse",
        analysis_run_id="run-sparse",
        pipeline_release="test-release",
        production_source_revision="native-commit-456",
        input_manifest_digest="sha256:" + "4" * 64,
        legacy_oracle_receipt_digest="sha256:" + "8" * 64,
        iq=reader,
        path_identity=_identity(manifest_digest="sha256:" + "4" * 64),
        calibration=_calibration(),
        reference=sparse,
        native=native,
        config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_BINDING, block_sample_count=25_000
        ),
    )
    assert receipt.status is MatchedAcceptanceStatus.INSUFFICIENT

    unestimable_qam, _, _ = _evaluate(qam_count=1)
    assert unestimable_qam.status is MatchedAcceptanceStatus.INSUFFICIENT
    assert "insufficient evidence" in unestimable_qam.reason


def test_decision_digest_and_sealed_reference_are_tamper_evident() -> None:
    samples = np.zeros(25_000, dtype=np.complex64)
    digest = sha256_digest(samples.astype("<c8").tobytes())
    decision = PilotWindowDecisionV1.create(
        source="legacy_reference",
        algorithm_id="sealed-retro-oracle",
        algorithm_version="reviewed-1",
        window_iq_digest=digest,
        window_index=0,
        sample_start=0,
        status=PilotDecisionStatus.EVALUATED,
        candidate=False,
        reason="sealed candidate-only RETRO oracle decision",
    )
    changed = decision.model_dump(mode="python")
    changed["candidate"] = True
    changed["epoch_sample"] = 1
    changed["cfo_hz"] = 2.0
    with pytest.raises(ValidationError, match="digest does not match"):
        PilotWindowDecisionV1.model_validate(changed)


def test_statistical_lower_bounds_have_known_edges() -> None:
    exact = binomial_lower_bounds(10, 10, alpha=0.05)
    assert exact.clopper_pearson_one_sided_lower == pytest.approx(0.05 ** (1 / 10))
    assert binomial_lower_bounds(0, 10, alpha=0.05).clopper_pearson_one_sided_lower == 0
    assert paired_student_t_lower_bound((-0.01,), alpha=0.05) is None
    assert paired_student_t_lower_bound((-0.01, -0.01), alpha=0.05) == pytest.approx(-0.01)
    assert paired_student_t_lower_bound((-1.0, 1.0), alpha=0.05) == pytest.approx(
        -6.3137515148,
        abs=1e-9,
    )


def test_receipt_rejects_tampered_counts_bounds_status_and_reason() -> None:
    receipt, _, _ = _evaluate()
    for field, value in (
        ("counts", {"n11": 99, "n10": 1, "n01": 0, "n00": 500}),
        ("status", "fail"),
        ("reason", "forged acceptance reason"),
    ):
        document = receipt.model_dump(mode="python")
        document[field] = value
        with pytest.raises(ValidationError, match="recomputed"):
            type(receipt).model_validate(document)


def test_published_v1_thresholds_cannot_be_relaxed() -> None:
    document = MatchedPilotAcceptanceConfigV1.create(detector_binding=_BINDING).model_dump(
        mode="python"
    )
    document["minimum_recovery_fraction"] = 0.0
    with pytest.raises(ValidationError, match="immutable"):
        MatchedPilotAcceptanceConfigV1.model_validate(document)
    NativeKnownPilotDecisionPort(
        MatchedPilotAcceptanceConfigV1.create(detector_binding=_BINDING),
        edge=StarlinkEdge.LOWER,
    )


def test_published_v1_acceptance_requires_explicit_lower_edge() -> None:
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=_BINDING)

    with pytest.raises(TypeError, match="edge"):
        NativeKnownPilotDecisionPort(config)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="edge"):
        native_template_digest()  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="V1 matched acceptance is lower-edge only"):
        NativeKnownPilotDecisionPort(config, edge=StarlinkEdge.UPPER)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="V1 matched acceptance is lower-edge only"):
        native_template_digest(StarlinkEdge.UPPER)  # type: ignore[arg-type]

    assert native_template_digest(StarlinkEdge.LOWER) == (
        "sha256:15455635bcdcfe0747f686ae317d235b5dfa54ae49c76b9741e6acc889d8a657"
    )


def test_sampled_band_gate_retains_300khz_doppler_and_full_pilot_support() -> None:
    config = MatchedPilotAcceptanceConfigV1.create(detector_binding=_BINDING)
    within = _calibration().model_copy(
        update={"uncertainty_lower_hz": -11_875.0, "uncertainty_upper_hz": 12_125.0}
    )
    outside = _calibration().model_copy(
        update={"uncertainty_lower_hz": -12_875.0, "uncertainty_upper_hz": 13_125.0}
    )
    assert calibration_search_domain_covers(within, config)
    assert not calibration_search_domain_covers(outside, config)


def test_campaign_enforces_exact_30_session_pairing_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _, _ = _evaluate()
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
    capture_receipt = CaptureModeAcceptanceHarness(RecordingStore(tmp_path / "bulk")).run_campaign(
        expectation,
        acceptance_id="accepted-capture-campaign",
        independent_radio_a_session_ids=tuple(f"a-{index}" for index in range(10)),
        independent_radio_b_session_ids=tuple(f"b-{index}" for index in range(10)),
        synchronized_pair_session_ids=tuple(f"pair-{index}" for index in range(10)),
        observed_utc_ns=1_800_000_100_000_000_000,
    )
    config = campaign_config_from_accepted_capture(
        campaign_id="campaign-30",
        capture_receipt=capture_receipt,
        detector_binding=_BINDING,
    )

    def stream(item: AcceptedCaptureStreamInventoryV1) -> AcceptanceCampaignStreamV1:
        stratum = next(
            declaration
            for declaration in config.strata
            if declaration.radio_id == item.radio_id and declaration.role is item.role
        )
        identity = ReceiverPathIdentityV1(
            radio_id=item.radio_id,
            radio_serial=item.radio_serial,
            receiver_id=1,
            physical_receiver_id=item.physical_receiver_id,
            capture_utc_ns=item.dwell_start_utc_ns,
            capture_end_utc_ns=item.dwell_end_utc_ns,
            hardware_epoch_id=item.hardware_epoch_id,
            session_id=item.session_id,
            stream_id=item.stream_id,
            manifest_digest=item.manifest_digest,
            profile_revision_digest=item.profile_revision_digest,
        )
        calibration = ReceiverFrequencyCalibrationV1.create(
            calibration_id=f"cal-{item.session_id}-{item.stream_id}",
            radio_id=item.radio_id,
            radio_serial=item.radio_serial,
            receiver_id=1,
            physical_receiver_id=item.physical_receiver_id,
            hardware_epoch_id=item.hardware_epoch_id,
            center_hz=125.0,
            uncertainty_lower_hz=120.0,
            uncertainty_upper_hz=130.0,
            valid_from_utc_ns=0,
            valid_until_utc_ns=2_000_000_000_000_000_000,
            method="reviewed-fixture",
            created_utc_ns=0,
            evidence=(
                CalibrationEvidenceV1(
                    kind="fixture",
                    uri=f"fixture://{item.session_id}-{item.stream_id}",
                    digest="sha256:" + "2" * 64,
                ),
            ),
        )
        receipt_values = base.model_dump(mode="python")
        receipt_values.update(
            artifact_id=f"receipt-{item.session_id}-{item.stream_id}",
            analysis_run_id=f"run-{item.session_id}-{item.stream_id}",
            legacy_oracle_receipt_digest=sha256_digest(
                f"oracle-{item.session_id}-{item.stream_id}".encode()
            ),
            input_manifest_digest=item.manifest_digest,
            path_identity=identity,
            calibration=calibration,
        )
        receipt = type(base).model_validate(receipt_values)
        return AcceptanceCampaignStreamV1(
            session_id=item.session_id,
            stream_id=item.stream_id,
            stratum_id=stratum.stratum_id,
            pairing_group_id=item.pairing_group_id,
            pipeline_run_id=receipt.analysis_run_id,
            pipeline_release=receipt.pipeline_release,
            production_source_revision=receipt.production_source_revision,
            analysis_product_digest=canonical_digest(receipt.model_dump(mode="json")),
            analysis_product_uri=(
                f"bulk://analysis/{item.session_id}/{receipt.analysis_run_id}/scientific/"
                f"matched-pilot-acceptance/{item.stream_id}/"
                "starlink.matched-acceptance.v1.json"
            ),
            receipt=receipt,
        )

    streams = tuple(stream(item) for item in config.capture_inventory)
    campaign = evaluate_acceptance_campaign(
        artifact_id="campaign-result",
        config=config,
        streams=streams,
    )
    assert campaign.status is MatchedAcceptanceStatus.INCONCLUSIVE
    assert campaign.observed_stream_count == 40
    assert campaign.observed_paired_session_count == 10
    assert campaign.production_accepted is False

    campaign_document = campaign.model_dump(mode="python")
    campaign_document["observed_paired_session_count"] = 9
    with pytest.raises(ValidationError, match="paired-session count"):
        type(campaign).model_validate(campaign_document)

    stream_document = streams[0].model_dump(mode="python")
    stream_document["analysis_product_uri"] = "artifact://invented/not-a-published-product.json"
    with pytest.raises(ValidationError, match="canonical receipt evidence"):
        AcceptanceCampaignStreamV1.model_validate(stream_document)

    config_document = config.model_dump(mode="python")
    config_document["capture_campaign_receipt_digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError, match="embedded receipt"):
        MatchedPilotAcceptanceCampaignConfigV1.model_validate(config_document)

    forged = tuple(
        item.model_copy(update={"pairing_group_id": "one-fake-group"})
        if item.pairing_group_id is not None
        else item
        for item in streams
    )
    with pytest.raises(ValueError, match="accepted capture evidence"):
        evaluate_acceptance_campaign(
            artifact_id="forged-campaign",
            config=config,
            streams=forged,
        )
    forged_run = (streams[0].model_copy(update={"pipeline_run_id": "forged-run"}), *streams[1:])
    with pytest.raises(ValueError, match="product/run binding"):
        evaluate_acceptance_campaign(
            artifact_id="forged-run-campaign",
            config=config,
            streams=forged_run,
        )


def test_analyzer_is_registry_callable_and_publishes_normal_product_sink() -> None:
    class NoProducts:
        def read_json(self, _requirement: ProductRequirement):
            return None

    class Sink:
        document = None

        def publish_json(self, product: ProductSpec, document):
            self.document = document
            return PublishedProduct(
                product=product,
                logical_uri="memory://matched.json",
                digest="sha256:" + "6" * 64,
                byte_size=1,
            )

    reference = _DecisionPort("legacy_reference", set(), qam=set())
    native = _DecisionPort("native", set(), qam=set())
    analyzer = MatchedPilotAcceptanceAnalyzer(
        config=MatchedPilotAcceptanceConfigV1.create(
            detector_binding=_BINDING, block_sample_count=25_000
        ),
        bindings=StaticMatchedAcceptanceBindingProvider(
            MatchedAcceptanceBinding(
                input_manifest_digest="sha256:" + "7" * 64,
                legacy_oracle_receipt_digest="sha256:" + "8" * 64,
                path_identity=_identity(manifest_digest="sha256:" + "7" * 64),
                calibration=None,
                reference=reference,
            )
        ),
        native=native,
    )
    registry = AnalyzerRegistry((analyzer,))
    sink = Sink()
    result = registry.get("matched-pilot-acceptance").analyze(
        AnalysisContext(
            session_id="session-a",
            run_id="run-a",
            pipeline_release="test-release",
            scope_key="radio-a-rx1",
        ),
        _ScheduledReader(),
        NoProducts(),
        sink,
    )

    assert result.outcome is StageOutcome.INSUFFICIENT_DATA
    assert result.products[0].product.kind == "starlink.matched-acceptance"
    assert sink.document["status"] == "insufficient"


def test_native_evidence_analyzer_seals_600_decisions_under_validated_release() -> None:
    binding = DetectorPipelineBindingV1.create(
        native_source_revision="a" * 40,
        native_source_tree_digest="sha256:" + "1" * 64,
        native_release_manifest_digest="sha256:" + "2" * 64,
        native_template_digest=native_template_digest(StarlinkEdge.LOWER),
        native_acquisition_configuration_digest=native_acquisition_configuration_digest(
            SymbolwiseAcquisitionConfig(maximum_probe_samples=25_000)
        ),
        native_qam_configuration_digest=native_qam_configuration_digest(),
        pipeline_release="sealed-release",
    )
    config = MatchedPilotAcceptanceConfigV1.create(
        detector_binding=binding,
        block_sample_count=25_000,
    )
    release_values = {
        "schema_version": 2,
        "kind": "validated-current-native-release",
        "pipeline_release": "sealed-release",
        "source_revision": "a" * 40,
        "git_tree": "b" * 40,
        "source_tree_digest": "sha256:" + "1" * 64,
        "release_metadata_digest": "sha256:" + "2" * 64,
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
            reason="release-local fixture decision",
        )
        for index in range(600)
    )

    class Scopes:
        def resolve(self, _context, _iq):
            return NativeEvidenceScopeBinding(
                input_manifest_digest="sha256:" + "3" * 64,
                path_identity=_identity(manifest_digest="sha256:" + "3" * 64),
                calibration=_calibration(),
            )

    class Releases:
        def resolve(self, _context):
            return release

    class Executor:
        def execute(self, **_kwargs):
            return NativeEvidenceExecutionResult(
                decisions=decisions,
                execution_environment_digest="sha256:" + "d" * 64,
                worker_output_digest="sha256:" + "e" * 64,
            )

    class NoProducts:
        def read_json(self, _requirement):
            return None

    class Sink:
        document = None

        def publish_json(self, product, document):
            self.document = document
            return PublishedProduct(
                product=product,
                logical_uri="memory://native-evidence.json",
                digest=canonical_digest(document),
                byte_size=1,
            )

    analyzer = NativeKnownPilotEvidenceAnalyzer(
        config=config,
        scopes=Scopes(),
        releases=Releases(),
        executor=Executor(),
    )
    sink = Sink()
    result = analyzer.analyze(
        AnalysisContext(
            session_id="session-a",
            run_id="native-run-a",
            pipeline_release="sealed-release",
            scope_key="stream-a",
        ),
        _ScheduledReader(),
        NoProducts(),
        sink,
    )

    assert result.outcome is StageOutcome.COMPLETE
    assert sink.document is not None
    product = NativeKnownPilotEvidenceProductV2.model_validate(sink.document)
    assert len(product.execution.decisions) == 600
    assert product.acceptance_eligible is False

    forged = product.model_dump(mode="python")
    forged["release"]["source_revision"] = "b" * 40
    with pytest.raises(ValidationError):
        NativeKnownPilotEvidenceProductV1.model_validate(forged)

    matched = MatchedPilotAcceptanceAnalyzer(
        config=config,
        bindings=StaticMatchedAcceptanceBindingProvider(
            MatchedAcceptanceBinding(
                input_manifest_digest="sha256:" + "3" * 64,
                legacy_oracle_receipt_digest="sha256:" + "8" * 64,
                path_identity=_identity(manifest_digest="sha256:" + "3" * 64),
                calibration=_calibration(),
                reference=_DecisionPort("legacy_reference", set(), qam=set()),
            )
        ),
        native=NativeKnownPilotDecisionPort(config, edge=StarlinkEdge.LOWER),
    )
    plan = AnalyzerRegistry((matched, analyzer)).plan()
    assert tuple(item.spec.key for item in plan) == (
        "native-known-pilot-evidence",
        "matched-pilot-acceptance",
    )
