from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.starlink import (
    MatchedAcceptanceBinding,
    MatchedPilotAcceptanceAnalyzer,
    NativeKnownPilotDecisionPort,
    StaticMatchedAcceptanceBindingProvider,
    SymbolwiseAcquisitionConfig,
    binomial_lower_bounds,
    evaluate_acceptance_campaign,
    evaluate_matched_known_pilot,
    native_acquisition_configuration_digest,
    native_qam_configuration_digest,
    native_template_digest,
    paired_student_t_lower_bound,
)
from leo.contracts import (
    AcceptanceCampaignStratumV1,
    AcceptanceCampaignStreamV1,
    AcceptanceStreamRole,
    AcceptedCaptureStreamInventoryV1,
    CalibrationEvidenceV1,
    DetectorPipelineBindingV1,
    MatchedAcceptanceStatus,
    MatchedPilotAcceptanceCampaignConfigV1,
    MatchedPilotAcceptanceConfigV1,
    PilotDecisionStatus,
    PilotWindowDecisionV1,
    ReceiverFrequencyCalibrationV1,
    ReceiverPathIdentityV1,
    sha256_digest,
)
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.domain.iq import IqBlock
from leo.pipeline import (
    AnalysisContext,
    AnalyzerRegistry,
    ProductRequirement,
    ProductSpec,
    PublishedProduct,
    StageOutcome,
)


def _binding() -> DetectorPipelineBindingV1:
    return DetectorPipelineBindingV1.create(
        legacy_source_revision="0bb80d14759fd8496b74e7d3219a690be18565a6",
        legacy_environment_digest="sha256:" + "9" * 64,
        legacy_configuration_digest="sha256:" + "a" * 64,
        native_source_revision="native-commit-456",
        native_template_digest=native_template_digest(),
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

    assert receipt.status is MatchedAcceptanceStatus.PASS
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
    assert failed.status is MatchedAcceptanceStatus.FAIL

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
    assert receipt.status is MatchedAcceptanceStatus.INCONCLUSIVE

    unestimable_qam, _, _ = _evaluate(qam_count=1)
    assert unestimable_qam.status is MatchedAcceptanceStatus.INCONCLUSIVE
    assert "interval" in unestimable_qam.reason


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
    NativeKnownPilotDecisionPort(MatchedPilotAcceptanceConfigV1.create(detector_binding=_BINDING))


def test_campaign_enforces_exact_30_session_pairing_inventory() -> None:
    base, _, _ = _evaluate()
    strata = tuple(
        AcceptanceCampaignStratumV1(
            stratum_id=f"{radio}-{role.value}",
            radio_id=f"radio-{radio}",
            radio_serial=f"serial-{radio}",
            receiver_id=1,
            physical_receiver_id=f"radio-{radio}-rx1",
            role=role,
        )
        for radio in ("a", "b")
        for role in (AcceptanceStreamRole.INDEPENDENT, AcceptanceStreamRole.PAIRED)
    )
    inventory = tuple(
        AcceptedCaptureStreamInventoryV1(
            session_id=f"pair-{index}" if role == "paired" else f"{radio}-only-{index}",
            stream_id=f"stream-{radio}-{role}-{index}",
            manifest_digest="sha256:" + ("1" if radio == "a" else "2") * 64,
            profile_revision_digest="sha256:" + "f" * 64,
            radio_id=f"radio-{radio}",
            radio_serial=f"serial-{radio}",
            physical_receiver_id=f"radio-{radio}-rx1",
            hardware_epoch_id=f"epoch-{radio}-1",
            station_topology_evidence_digest="sha256:" + "7" * 64,
            role=AcceptanceStreamRole(role),
            pairing_group_id=f"pair-{index}" if role == "paired" else None,
            synchronization_grade=("degraded" if role == "paired" else "not_requested"),
            estimated_overlap_fraction=0.99 if role == "paired" else None,
            guaranteed_overlap_fraction=0.0 if role == "paired" else None,
            start_skew_uncertainty_ns=20 if role == "paired" else None,
            dwell_start_utc_ns=1_000,
            dwell_end_utc_ns=60_000_001_000,
        )
        for radio in ("a", "b")
        for role in ("independent", "paired")
        for index in range(10)
    )
    config = MatchedPilotAcceptanceCampaignConfigV1.create(
        campaign_id="campaign-30",
        capture_campaign_receipt_digest="sha256:" + "5" * 64,
        detector_binding=_BINDING,
        strata=strata,
        capture_inventory=inventory,
    )

    def stream(radio: str, role: str, index: int) -> AcceptanceCampaignStreamV1:
        paired = role == "paired"
        session_id = f"pair-{index}" if paired else f"{radio}-only-{index}"
        stream_id = f"stream-{radio}-{role}-{index}"
        identity = _identity(
            radio=radio,
            session_id=session_id,
            stream_id=stream_id,
            manifest_digest="sha256:" + ("1" if radio == "a" else "2") * 64,
        )
        receipt_values = base.model_dump(mode="python")
        receipt_values.update(
            artifact_id=f"receipt-{radio}-{role}-{index}",
            analysis_run_id=f"run-{radio}-{role}-{index}",
            legacy_oracle_receipt_digest=sha256_digest(f"oracle-{radio}-{role}-{index}".encode()),
            input_manifest_digest="sha256:" + ("1" if radio == "a" else "2") * 64,
            path_identity=identity,
            calibration=_calibration(radio),
        )
        receipt = type(base).model_validate(receipt_values)
        return AcceptanceCampaignStreamV1(
            session_id=session_id,
            stream_id=stream_id,
            stratum_id=f"{radio}-{role}",
            pairing_group_id=f"pair-{index}" if paired else None,
            pipeline_run_id=receipt.analysis_run_id,
            pipeline_release=receipt.pipeline_release,
            production_source_revision=receipt.production_source_revision,
            analysis_product_digest=sha256_digest(receipt.artifact_id.encode()),
            analysis_product_uri=f"artifact://{receipt.artifact_id}",
            receipt=receipt,
        )

    streams = tuple(
        stream(radio, role, index)
        for radio in ("a", "b")
        for role in ("independent", "paired")
        for index in range(10)
    )
    campaign = evaluate_acceptance_campaign(
        artifact_id="campaign-result",
        config=config,
        streams=streams,
    )
    assert campaign.status is MatchedAcceptanceStatus.PASS
    assert campaign.observed_stream_count == 40
    assert campaign.observed_paired_session_count == 10
    assert campaign.production_accepted is False

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
            )
        ),
        reference=reference,
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
