from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace

import numpy as np
import pytest
from pydantic import ValidationError

from leo.analysis.graphs import POWER as LEGACY_POWER_PRODUCT
from leo.analysis.graphs import WATERFALL as LEGACY_WATERFALL_PRODUCT
from leo.analysis.standard import (
    GLRT64_TRAJECTORY_TABLE_PRODUCT,
    NUMERICAL_WATERFALL_PRODUCT,
    PATH_REPORT_INPUTS,
    POWER_TIMELINE_PRODUCT,
    PROBE_SCHEDULE_INPUTS,
    QUALITY_INPUTS,
    STANDARD_SOURCE_BINDING_SPECS,
    STANDARD_SOURCE_BOUND_STAGE_OUTPUTS,
    TRAJECTORY_BANK_INPUTS,
    TRAJECTORY_FEEDBACK_INPUTS,
    TRAJECTORY_FEEDBACK_OUTPUTS,
    PathReportInputs,
    ReceiverStandardConfig,
    build_path_standard_report,
    build_probe_schedule,
    build_standard_source_binding,
    build_standard_source_bindings,
    receiver_standard_configuration_digest,
    receiver_standard_implementation_digest,
    reduce_paired_radios,
    reduce_radio,
    run_receiver_standard,
)
from leo.analysis.standard.reports import reusable_trajectory_documents
from leo.analysis.starlink.acquisition import NumericalStatus
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
)
from leo.analysis.starlink.trajectories import (
    PolynomialTrajectory,
    TrajectoryBankResult,
    TrajectoryFamily,
)
from leo.analysis.starlink.trajectory_feedback import (
    TrajectoryFeedbackConfig,
    build_glrt64_trajectory_table,
)
from leo.analysis.waterfall import WaterfallConfig
from leo.contracts.digests import canonical_digest
from leo.contracts.radio import IqBlockMetadataV1, NanosecondIntervalV1
from leo.contracts.standard_pipeline import (
    AssociationStatus,
    FrequencyReference,
    PairTimingEvidenceV1,
    PathStandardReportV1,
    ReceiverFrequencyReferenceV1,
    StandardPairInputBindV2,
    StandardPathInputBindV2,
    StandardScientificStatus,
    StandardTrajectoryV1,
    StreamTimingEvidenceV1,
)
from leo.domain.iq import IqBlock

_SESSION = "production-24h-20260819-01-trial-00000132"
_MANIFEST = "sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d"
_SYNC = canonical_digest({"fixture": "trial-132-sync"})


def test_probe_schedule_is_exact_bounded_and_digest_stable() -> None:
    first = build_probe_schedule(sample_rate_hz=2_500_000, sample_count=150_000_000)
    second = build_probe_schedule(sample_rate_hz=2_500_000, sample_count=150_000_000)

    assert first == second
    assert first.returned_probe_count == 1_200
    assert first.truncated_probe_count == 0
    assert first.probes[0].sample_start == 0
    assert first.probes[0].sample_count == 50_000
    assert first.probes[-1].sample_start == 149_875_000
    assert first.probes[-1].time_s == 59.95
    assert len({item.probe_id for item in first.probes}) == 1_200


def test_uncalibrated_prior_cannot_smuggle_frequency_authority() -> None:
    with pytest.raises(ValidationError, match="cannot carry calibration authority"):
        ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR,
            center_frequency_hz=1_709_687_500.0,
        )


def test_standard_v2_product_dependencies_are_exact_and_additive() -> None:
    assert POWER_TIMELINE_PRODUCT.model_dump(mode="json") == {
        "kind": "standard.power-timeline",
        "schema_version": 2,
        "role": "scientific",
        "media_type": "application/json",
    }
    assert NUMERICAL_WATERFALL_PRODUCT.kind == "standard.numerical-waterfall"
    assert POWER_TIMELINE_PRODUCT.kind != "power.summary"
    assert NUMERICAL_WATERFALL_PRODUCT.kind != "waterfall.tiles"
    assert (LEGACY_POWER_PRODUCT.kind, LEGACY_POWER_PRODUCT.schema_version) == (
        "power.summary",
        1,
    )
    assert (LEGACY_WATERFALL_PRODUCT.kind, LEGACY_WATERFALL_PRODUCT.schema_version) == (
        "waterfall.tiles",
        1,
    )
    assert tuple(item.kind for item in QUALITY_INPUTS) == ("standard.path-input-bind",)
    assert tuple(item.kind for item in PROBE_SCHEDULE_INPUTS) == ("standard.path-input-bind",)
    assert tuple(item.kind for item in TRAJECTORY_BANK_INPUTS) == ("standard.pilot-scan",)
    assert tuple(item.kind for item in TRAJECTORY_FEEDBACK_INPUTS) == (
        "standard.pilot-scan",
        "standard.trajectory-bank",
    )
    assert tuple(item.kind for item in TRAJECTORY_FEEDBACK_OUTPUTS) == (
        "standard.trajectory-feedback",
        GLRT64_TRAJECTORY_TABLE_PRODUCT.kind,
    )
    assert {item.kind: item.producer_stage_key for item in PATH_REPORT_INPUTS} == {
        "standard.path-input-bind": "path-input-bind",
        "standard.probe-schedule": "path-probe-schedule",
        "quality.summary": "path-quality",
        "standard.power-timeline": "path-power",
        "standard.numerical-waterfall": "path-waterfall",
        "standard.pilot-scan": "path-pilot-scan",
        "standard.trajectory-bank": "path-trajectory-bank",
        "standard.trajectory-feedback": "path-trajectory-feedback",
        "standard.glrt64-trajectory-table": "path-trajectory-feedback",
    }
    assert all(item.require_available for item in PATH_REPORT_INPUTS)
    declared_source_bound_outputs = {
        (stage_key, product.kind, product.schema_version)
        for stage_key, products in STANDARD_SOURCE_BOUND_STAGE_OUTPUTS.items()
        for product in products
    }
    assert {
        (spec.stage_key, spec.product_kind, spec.product_schema_version)
        for spec in STANDARD_SOURCE_BINDING_SPECS
    } == declared_source_bound_outputs
    assert sum(len(products) for products in STANDARD_SOURCE_BOUND_STAGE_OUTPUTS.values()) == 8
    assert {spec.wrapper_kind for spec in STANDARD_SOURCE_BINDING_SPECS}.isdisjoint(
        {
            product.kind
            for products in STANDARD_SOURCE_BOUND_STAGE_OUTPUTS.values()
            for product in products
        }
    )


def test_path_binding_rejects_fabricated_legacy_lineage_and_digest_mutation() -> None:
    values = _path_binding_values()
    fabricated = {**values, "physical_receiver_id": "invented-rx"}
    with pytest.raises(ValidationError, match="cannot fabricate"):
        StandardPathInputBindV2.model_validate(
            {**fabricated, "binding_digest": canonical_digest(fabricated)}
        )
    with pytest.raises(ValidationError, match="digest does not match"):
        StandardPathInputBindV2.model_validate({**values, "binding_digest": "sha256:" + "0" * 64})


def test_radio_and_pair_reducers_are_deterministic_product_only_and_noncoherent() -> None:
    stream0_start = 1_787_121_029_925_651_245
    stream1_start = 1_787_121_029_924_226_035
    stream0 = (
        _path("stream-0", "radio-0", 0, stream0_start, 253_000.0),
        _path("stream-0", "radio-0", 1, stream0_start, 253_300.0),
    )
    stream1 = (
        _path("stream-1", "radio-1", 0, stream1_start, 253_100.0),
        _path("stream-1", "radio-1", 1, stream1_start, 253_200.0),
    )

    radio0 = reduce_radio(tuple(reversed(stream0)), declared_receiver_ids=(0, 1))
    radio1 = reduce_radio(stream1, declared_receiver_ids=(0, 1))
    timing = PairTimingEvidenceV1(
        synchronization_inventory_digest=_SYNC,
        union_start_utc_ns=stream1_start,
        union_end_utc_ns=stream0_start + 60_000_000_000,
        estimated_overlap_start_utc_ns=stream0_start,
        estimated_overlap_end_utc_ns=stream1_start + 60_000_000_000,
        estimated_start_skew_ns=1_425_210,
        start_skew_uncertainty_ns=301_027_179,
        guaranteed_overlap_ns=0,
        synchronization_grade="degraded",
        phase_coherent=False,
    )
    binding = _pair_binding(timing)
    paired = reduce_paired_radios((radio1, radio0), binding=binding)
    repeated = reduce_paired_radios((radio0, radio1), binding=binding)

    assert radio0.association_status is AssociationStatus.EVALUATED
    assert len(radio0.associations) == 1
    assert paired == repeated
    assert paired.timing.estimated_start_skew_ns == 1_425_210
    assert paired.timing.union_end_utc_ns - paired.timing.union_start_utc_ns == 60_001_425_210
    assert paired.phase_coherent is False
    assert paired.candidate_only is True
    assert paired.specificity_claimed is False
    assert paired.payload_decoded is False
    assert len(paired.radios) == 2
    assert len(tuple(path for radio in paired.radios for path in radio.paths)) == 4


def test_uncalibrated_prior_preserves_tracks_but_disables_association() -> None:
    start = 1_787_121_029_925_651_245
    paths = (
        _path("stream-0", "radio-0", 0, start, 253_000.0, calibrated=False),
        _path("stream-0", "radio-0", 1, start, 253_300.0, calibrated=False),
    )

    radio = reduce_radio(paths, declared_receiver_ids=(0, 1))

    assert radio.association_status is AssociationStatus.UNAVAILABLE_UNCALIBRATED_PRIOR
    assert radio.associations == ()
    assert len(radio.unmatched_trajectory_ids) == 2
    assert all(path.trajectories for path in radio.paths)


def test_reducers_reject_foreign_or_missing_children() -> None:
    start = 1_787_121_029_925_651_245
    one = _path("stream-0", "radio-0", 0, start, 253_000.0)
    foreign = _path("stream-1", "radio-1", 1, start, 253_000.0)

    with pytest.raises(ValueError, match="exactly match declared"):
        reduce_radio((one,), declared_receiver_ids=(0, 1))
    with pytest.raises(ValueError, match="stream_id"):
        reduce_radio((one, foreign), declared_receiver_ids=(0, 1))


def test_reducers_propagate_dropout_reject_wrong_overlap_and_keep_cfo_sign() -> None:
    start = 1_787_121_029_925_651_245
    dropout = _path(
        "stream-0",
        "radio-0",
        0,
        start,
        10_000.0,
        status=StandardScientificStatus.PARTIAL,
        truncated_candidate_count=3,
    )
    complete = _path("stream-0", "radio-0", 1, start, 10_100.0)
    radio = reduce_radio((dropout, complete), declared_receiver_ids=(0, 1))

    assert radio.status is StandardScientificStatus.PARTIAL
    assert radio.child_truncated_candidate_count == 3

    other_start = start - 1_425_210
    other_paths = (
        _path("stream-1", "radio-1", 0, other_start, 10_000.0),
        _path("stream-1", "radio-1", 1, other_start, 10_100.0),
    )
    other_radio = reduce_radio(other_paths, declared_receiver_ids=(0, 1))
    wrong_overlap = PairTimingEvidenceV1(
        synchronization_inventory_digest=_SYNC,
        union_start_utc_ns=other_start,
        union_end_utc_ns=start + 60_000_000_000,
        estimated_overlap_start_utc_ns=start + 1,
        estimated_overlap_end_utc_ns=other_start + 60_000_000_000,
        estimated_start_skew_ns=1_425_210,
        start_skew_uncertainty_ns=301_027_179,
        guaranteed_overlap_ns=0,
        synchronization_grade="degraded",
        phase_coherent=False,
    )
    with pytest.raises(ValueError, match="exact child report timelines"):
        reduce_paired_radios((radio, other_radio), binding=_pair_binding(wrong_overlap))
    foreign_values = _pair_binding_values(wrong_overlap)
    foreign_values["manifest_digest"] = canonical_digest({"manifest": "foreign"})
    foreign_binding = StandardPairInputBindV2.model_validate(
        {**foreign_values, "binding_digest": canonical_digest(foreign_values)}
    )
    with pytest.raises(ValueError, match="subject binding"):
        reduce_paired_radios((radio, other_radio), binding=foreign_binding)

    sign_paths = (
        _path(
            "stream-sign",
            "radio-sign",
            0,
            start,
            10_000.0,
            center_frequency_hz=1_000_000.0,
        ),
        _path(
            "stream-sign",
            "radio-sign",
            1,
            start,
            -10_000.0,
            center_frequency_hz=980_000.0,
        ),
    )
    signed = reduce_radio(sign_paths, declared_receiver_ids=(0, 1))
    assert signed.associations == ()
    assert len(signed.unmatched_trajectory_ids) == 2


def test_complete_receiver_runner_is_exact_repeatable_and_keeps_uncalibrated_prior(
    monkeypatch,
) -> None:
    def fake_detect(
        _samples,
        sample_rate_hz,
        *,
        sample_start,
        calibration,
        acquisition_config,
        maximum_scored_candidates=4,
    ) -> PilotProbeDetection:
        del calibration, acquisition_config, maximum_scored_candidates
        time_s = sample_start / sample_rate_hz
        negative = (sample_start // 50) % 10 == 0
        scores = tuple(
            PilotMethodScore(
                method,
                0.0 if negative else 0.9,
                0.1 if method is not PilotMethod.QAM_ACCURACY else None,
                -0.1 if negative else 0.8,
                0.0,
                250_000.0 - 2_000.0 * time_s + 20.0 * time_s**2,
            )
            for method in PilotMethod
        )
        return PilotProbeDetection(
            NumericalStatus.COMPLETE,
            sample_start,
            time_s,
            0,
            scores[0].tracking_cfo_hz,
            scores,
            0.9,
            0.1,
            "synthetic multi-method candidate",
            source_candidate_count=1,
            candidates=(
                PilotMethodCandidate(
                    0,
                    0,
                    scores[0].tracking_cfo_hz,
                    scores,
                    0.9,
                    0.1,
                ),
            ),
        )

    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.detect_pilot_methods", fake_detect
    )
    monkeypatch.setattr(
        "leo.analysis.starlink.trajectory_feedback.detect_pilot_method_candidates",
        fake_detect,
    )
    config = ReceiverStandardConfig(
        quality_block_samples=333,
        power_block_samples=271,
        waterfall=WaterfallConfig(
            fft_samples=20,
            frequency_bins=10,
            maximum_time_bins=8,
            block_samples=257,
        ),
        feedback=TrajectoryFeedbackConfig(
            maximum_outer_windows=4,
            maximum_replayed_families=16,
            maximum_workers=2,
        ),
    )
    schedule = build_probe_schedule(
        sample_rate_hz=1_000,
        sample_count=4_000,
        maximum_coarse_windows=4,
    )
    bind_values = {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
        "session_id": "synthetic-session",
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 1,
        "manifest_digest": canonical_digest({"manifest": "synthetic"}),
        "raw_integrity_attestation_digest": canonical_digest({"raw-integrity": "synthetic"}),
        "selected_stream_digest": canonical_digest({"stream": "synthetic"}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": "synthetic"}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": "synthetic"}),
        "synchronization_inventory_digest": canonical_digest({"sync": "synthetic"}),
        "profile_revision_digest": canonical_digest({"profile": "synthetic"}),
        "capture_plan_digest": canonical_digest({"plan": "synthetic"}),
        "receiver_settings_digest": canonical_digest({"settings": "synthetic"}),
        "science_configuration_digest": receiver_standard_configuration_digest(config),
        "science_implementation_digest": receiver_standard_implementation_digest(),
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": 1_000_000,
        "sample_rate_hz": 1_000,
        "declared_sample_count": 4_000,
        "timing": _timing(10_000_000_000).model_dump(mode="json"),
        "frequency_reference": ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.UNCALIBRATED_PRIOR
        ).model_dump(mode="json"),
    }
    inputs = PathReportInputs(
        input_bind=StandardPathInputBindV2.model_validate(
            {**bind_values, "binding_digest": canonical_digest(bind_values)}
        ),
        schedule=schedule,
        quality_clipping_abs_threshold=32_767,
        power_window_samples=1_000,
        waterfall_config_digest=config.waterfall.digest,
        maximum_scored_candidates_per_probe=(config.feedback.maximum_scored_candidates_per_probe),
        maximum_replayed_families=config.feedback.maximum_replayed_families,
    )
    first = run_receiver_standard(_DualReader(), inputs, config=config)
    second = run_receiver_standard(_DualReader(), inputs, config=config)

    assert first == second
    assert first.products.report.status is StandardScientificStatus.COMPLETE
    assert len(first.products.pilot_certificates) == 80
    assert {item.polynomial_degree for item in first.products.report.trajectories} == {1, 2, 3}
    assert len(first.documents["standard.power-timeline"]["timeline"]) == 4
    assert "power.summary" not in first.documents
    assert "waterfall.tiles" not in first.documents
    assert first.documents["standard.numerical-waterfall"]["schema_version"] == 2
    assert {item.kind for item in first.products.report.products} >= {
        "standard.power-timeline",
        "standard.numerical-waterfall",
    }
    product_digests = {item.kind: item.content_digest for item in first.products.report.products}
    assert set(product_digests) == {
        "standard.path-input-bind",
        "standard.probe-schedule",
        "quality.summary",
        "standard.power-timeline",
        "standard.numerical-waterfall",
        "standard.pilot-scan",
        "standard.trajectory-bank",
        "standard.trajectory-feedback",
        "standard.glrt64-trajectory-table",
    }
    assert product_digests["standard.path-input-bind"] == canonical_digest(
        inputs.input_bind.model_dump(mode="json")
    )
    assert product_digests["standard.probe-schedule"] == canonical_digest(
        inputs.schedule.model_dump(mode="json")
    )
    assert product_digests["standard.trajectory-bank"] == canonical_digest(
        first.documents["standard.trajectory-bank"]
    )
    assert product_digests["standard.glrt64-trajectory-table"] == canonical_digest(
        first.documents["standard.glrt64-trajectory-table"]
    )
    serialized = repr(first.documents) + first.products.report.model_dump_json()
    assert "standard-exploratory-zero-baseband-prior" not in serialized
    assert "calibration_sha256" not in serialized
    assert (
        first.products.report.frequency_reference.reference is FrequencyReference.UNCALIBRATED_PRIOR
    )
    assert first.products.report.frequency_reference.calibration_digest is None

    def rebuild(
        documents,
        source_bindings=first.source_bindings,
        report_inputs=inputs,
    ):
        return build_path_standard_report(
            report_inputs,
            quality_document=documents["quality.summary"],
            power_document=documents["standard.power-timeline"],
            waterfall_document=documents["standard.numerical-waterfall"],
            pilot_document=documents["standard.pilot-scan"],
            trajectory_document=documents["standard.trajectory-bank"],
            feedback_document=documents["standard.trajectory-feedback"],
            trajectory_table_document=documents["standard.glrt64-trajectory-table"],
            source_binding_documents={
                spec.wrapper_kind: source_bindings[spec.wrapper_kind]
                for spec in STANDARD_SOURCE_BINDING_SPECS
            },
        )

    zero_documents = deepcopy(first.documents)
    zero_documents["standard.trajectory-bank"]["trajectories"] = []
    zero_documents["standard.trajectory-bank"]["families"] = []
    zero_documents["standard.trajectory-bank"]["replayed_representatives"] = []
    zero_documents["standard.trajectory-feedback"]["trajectory_bank_digest"] = canonical_digest(
        zero_documents["standard.trajectory-bank"]
    )
    zero_documents["standard.trajectory-feedback"]["results"] = []
    zero_documents["standard.glrt64-trajectory-table"]["trajectory_bank_digest"] = canonical_digest(
        zero_documents["standard.trajectory-bank"]
    )
    zero_documents["standard.glrt64-trajectory-table"]["trajectory_feedback_digest"] = (
        canonical_digest(zero_documents["standard.trajectory-feedback"])
    )
    zero_documents["standard.glrt64-trajectory-table"]["trajectories"] = []
    zero_source_documents = {
        **zero_documents,
        "standard.probe-schedule": inputs.schedule.model_dump(mode="json"),
    }
    zero_bindings = build_standard_source_bindings(inputs.input_bind, zero_source_documents)
    positive_zero = rebuild(
        zero_documents, zero_bindings, replace(inputs, maximum_replayed_families=1)
    )
    assert positive_zero.report.trajectories == ()
    for invalid_maximum in (-1, 0, True):
        with pytest.raises(
            ValueError,
            match="maximum_replayed_families must be a positive integer",
        ):
            rebuild(
                zero_documents,
                zero_bindings,
                replace(inputs, maximum_replayed_families=invalid_maximum),
            )

    foreign_values = {
        **inputs.input_bind.model_dump(mode="json", exclude={"binding_digest"}),
        "session_id": "foreign-session",
        "stream_id": "foreign-stream",
        "radio_id": "foreign-radio",
        "manifest_digest": canonical_digest({"manifest": "foreign"}),
        "selected_stream_digest": canonical_digest({"stream": "foreign"}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": "foreign"}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": "foreign"}),
    }
    foreign_bind = StandardPathInputBindV2.model_validate(
        {**foreign_values, "binding_digest": canonical_digest(foreign_values)}
    )
    foreign = run_receiver_standard(
        _DualReader(),
        replace(inputs, input_bind=foreign_bind),
        config=config,
    )
    raw_science_kinds = {
        "quality.summary",
        "standard.power-timeline",
        "standard.numerical-waterfall",
        "standard.pilot-scan",
        "standard.trajectory-bank",
        "standard.trajectory-feedback",
        "standard.glrt64-trajectory-table",
    }
    assert {kind: first.documents[kind] for kind in raw_science_kinds} == {
        kind: foreign.documents[kind] for kind in raw_science_kinds
    }
    assert all(
        first.source_bindings[spec.wrapper_kind] != foreign.source_bindings[spec.wrapper_kind]
        for spec in STANDARD_SOURCE_BINDING_SPECS
    )
    with pytest.raises(ValueError, match="does not bind the exact Standard path source chain"):
        rebuild(foreign.documents, foreign.source_bindings)
    for spec in STANDARD_SOURCE_BINDING_SPECS:
        substituted_wrapper = deepcopy(first.source_bindings)
        substituted_wrapper[spec.wrapper_kind] = foreign.source_bindings[spec.wrapper_kind]
        with pytest.raises(ValueError, match=spec.wrapper_kind):
            rebuild(first.documents, substituted_wrapper)
    feedback_spec = next(
        spec
        for spec in STANDARD_SOURCE_BINDING_SPECS
        if spec.wrapper_kind == "standard.trajectory-feedback-source-bind"
    )
    with pytest.raises(ValueError, match="predecessors bind different path inputs"):
        build_standard_source_binding(
            feedback_spec,
            first.documents["standard.trajectory-feedback"],
            predecessor_binding_documents={
                "standard.pilot-source-bind": foreign.source_bindings["standard.pilot-source-bind"],
                "standard.trajectory-bank-source-bind": first.source_bindings[
                    "standard.trajectory-bank-source-bind"
                ],
            },
        )

    substitutions = []
    wrong_receiver = deepcopy(first.documents)
    wrong_receiver["standard.power-timeline"]["receiver_ids"] = [0]
    substitutions.append(wrong_receiver)
    wrong_quality_receiver = deepcopy(first.documents)
    wrong_quality_receiver["quality.summary"]["receivers"][0]["receiver_id"] = 0
    substitutions.append(wrong_quality_receiver)
    wrong_waterfall_gap = deepcopy(first.documents)
    wrong_waterfall_gap["standard.numerical-waterfall"]["coverage"]["gap_count"] += 1
    substitutions.append(wrong_waterfall_gap)
    partial_power = deepcopy(first.documents)
    partial_power["standard.power-timeline"]["observed_sample_count"] -= 1
    partial_power["standard.power-timeline"]["missing_sample_count"] += 1
    partial_power["standard.power-timeline"]["coverage_fraction"] = 3_999 / 4_000
    partial_power["standard.power-timeline"]["timeline"][-1]["observed_sample_count"] -= 1
    substitutions.append(partial_power)
    wrong_pilot_geometry = deepcopy(first.documents)
    wrong_pilot_geometry["standard.pilot-scan"]["probe_samples"] += 1
    substitutions.append(wrong_pilot_geometry)
    wrong_schedule_bind = deepcopy(first.documents)
    wrong_schedule_bind["standard.pilot-scan"]["probe_schedule_digest"] = "sha256:" + "0" * 64
    substitutions.append(wrong_schedule_bind)
    wrong_bank_predecessor = deepcopy(first.documents)
    wrong_bank_predecessor["standard.trajectory-bank"]["pilot_scan_digest"] = "sha256:" + "0" * 64
    substitutions.append(wrong_bank_predecessor)
    wrong_bank_observations = deepcopy(first.documents)
    wrong_bank_observations["standard.trajectory-bank"]["observation_count"] += 1
    substitutions.append(wrong_bank_observations)
    assert first.documents["standard.trajectory-feedback"]["results"]
    wrong_feedback = deepcopy(first.documents)
    wrong_feedback["standard.trajectory-feedback"]["results"][0]["baseline_margin"] += 0.01
    substitutions.append(wrong_feedback)
    wrong_table = deepcopy(first.documents)
    wrong_table["standard.glrt64-trajectory-table"]["trajectories"][0]["coefficients_hz"][-1] += 1.0
    substitutions.append(wrong_table)
    wrong_table_digest = deepcopy(first.documents)
    wrong_table_digest["standard.glrt64-trajectory-table"]["trajectory_feedback_digest"] = (
        "sha256:" + "0" * 64
    )
    substitutions.append(wrong_table_digest)
    nonfinite = deepcopy(first.documents)
    nonfinite["quality.summary"]["coverage_fraction"] = float("nan")
    substitutions.append(nonfinite)
    infinite = deepcopy(first.documents)
    infinite["standard.numerical-waterfall"]["frequency_bin_centers_hz"][0] = float("inf")
    substitutions.append(infinite)
    for substituted in substitutions:
        with pytest.raises((ValueError, ValidationError)):
            rebuild(substituted)


def test_replay_metrics_belong_only_to_the_exact_selected_trajectory() -> None:
    selected = _polynomial("selected", degree=2)
    unselected = _polynomial("unselected", degree=3)
    family = TrajectoryFamily(
        family_id=canonical_digest({"family": "shared"}),
        representative_trajectory_id=selected.trajectory_id,
        member_trajectory_ids=(selected.trajectory_id, unselected.trajectory_id),
        start_s=0.0,
        end_s=4.0,
    )
    bank = TrajectoryBankResult(
        config_digest=canonical_digest({"config": "test"}),
        trajectories=(selected, unselected),
        families=(family,),
        observation_count=12,
        truncated_trajectory_count=0,
    )
    replay = tuple(
        {
            "family_id": family.family_id,
            "trajectory_id": selected.trajectory_id,
            "detector_method": "glrt64",
            "margin_delta": value,
        }
        for value in (0.1, 0.3)
    )

    table = build_glrt64_trajectory_table(
        bank,
        ((family.family_id, selected),),
        replay,
    )
    by_id = {item["trajectory_id"]: item for item in table}

    assert by_id[selected.trajectory_id]["selected_for_correction"] is True
    assert by_id[selected.trajectory_id]["corrected_glrt64_probe_count"] == 2
    assert by_id[selected.trajectory_id]["median_glrt64_margin_delta"] == pytest.approx(0.2)
    assert by_id[unselected.trajectory_id]["selected_for_correction"] is False
    assert by_id[unselected.trajectory_id]["corrected_glrt64_probe_count"] == 0
    assert by_id[unselected.trajectory_id]["median_glrt64_margin_delta"] is None


def test_reusable_trajectory_bytes_do_not_depend_on_run_membership() -> None:
    base = {
        "schema_version": 1,
        "scope_key": "stream-0.rx-0",
        "candidate_only": True,
        "frequency_coordinate": "baseband_cfo_hz",
        "frequency_reference": "uncalibrated_prior",
    }
    documents_a = {
        "starlink.pilot-method-detections": {
            **base,
            "run_id": "run-a",
            "methods": [],
            "detections": [],
        },
        "starlink.polynomial-trajectories": {
            **base,
            "run_id": "run-a",
            "trajectories": [],
            "families": [],
        },
        "starlink.trajectory-redetection": {**base, "run_id": "run-a", "results": []},
        "starlink.glrt64-trajectory-table": {
            **base,
            "run_id": "run-a",
            "trajectories": [],
        },
    }
    documents_b = {
        kind: {**document, "run_id": "run-b", "scope_key": "another-membership-key"}
        for kind, document in documents_a.items()
    }

    stable_a = reusable_trajectory_documents(documents_a)
    stable_b = reusable_trajectory_documents(documents_b)

    assert stable_a == stable_b
    assert canonical_digest(stable_a) == canonical_digest(stable_b)
    assert "run-a" not in repr(stable_a) and "run-b" not in repr(stable_b)


def _path(
    stream_id: str,
    radio_id: str,
    receiver_id: int,
    start_utc_ns: int,
    cfo_hz: float,
    *,
    calibrated: bool = True,
    center_frequency_hz: float = 1_709_687_500.0,
    status: StandardScientificStatus = StandardScientificStatus.COMPLETE,
    truncated_candidate_count: int = 0,
) -> PathStandardReportV1:
    trajectory_values = {
        "schema_version": 1,
        "trajectory_id": canonical_digest(
            {"stream": stream_id, "receiver": receiver_id, "cfo": cfo_hz}
        ),
        "family_id": canonical_digest({"stream": stream_id, "family": receiver_id}),
        "method": "glrt64",
        "polynomial_degree": 2,
        "reference_time_s": 30.0,
        "coefficients_hz": [20.0, -2_000.0, cfo_hz],
        "start_s": 6.2,
        "end_s": 39.0,
        "point_count": 120,
        "residual_rms_hz": 400.0,
        "bic": 100.0,
        "em_iterations": 3,
        "fit_matches_well": True,
        "selected_for_correction": True,
        "corrected_glrt64_probe_count": 656,
        "median_glrt64_margin_delta": 0.12,
    }
    trajectory = StandardTrajectoryV1.model_validate(trajectory_values)
    timing = _timing(start_utc_ns)
    frequency = (
        ReceiverFrequencyReferenceV1(
            reference=FrequencyReference.CALIBRATED,
            center_frequency_hz=center_frequency_hz,
            uncertainty_hz=100.0,
            calibration_digest=canonical_digest(
                {"stream": stream_id, "receiver": receiver_id, "calibration": "fixture"}
            ),
        )
        if calibrated
        else ReceiverFrequencyReferenceV1(reference=FrequencyReference.UNCALIBRATED_PRIOR)
    )
    values = {
        "schema_version": 1,
        "session_id": _SESSION,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "receiver_id": receiver_id,
        "manifest_digest": _MANIFEST,
        "synchronization_inventory_digest": _SYNC,
        "pipeline_family": "standard-glrt64-v2",
        "status": status,
        "reason": "synthetic complete candidate-only path",
        "sample_rate_hz": 2_500_000,
        "declared_sample_count": 150_000_000,
        "observed_sample_count": 150_000_000,
        "coverage_fraction": 1.0,
        "timing": timing.model_dump(mode="json"),
        "frequency_reference": frequency.model_dump(mode="json"),
        "probe_schedule_digest": canonical_digest({"schedule": "fixture"}),
        "method_names": ["glrt64"],
        "initial_glrt64": [],
        "trajectories": [trajectory.model_dump(mode="json")],
        "products": [],
        "truncated_candidate_count": truncated_candidate_count,
        "truncated_trajectory_count": 0,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return PathStandardReportV1(**values, report_digest=canonical_digest(values))


def _timing(start_utc_ns: int) -> StreamTimingEvidenceV1:
    return StreamTimingEvidenceV1(
        first_estimate_utc_ns=start_utc_ns,
        first_earliest_utc_ns=start_utc_ns - 100_000,
        first_latest_utc_ns=start_utc_ns + 100_000,
        last_estimate_utc_ns=start_utc_ns + 60_000_000_000,
        last_earliest_utc_ns=start_utc_ns + 59_999_900_000,
        last_latest_utc_ns=start_utc_ns + 60_000_100_000,
    )


def _pair_binding(timing: PairTimingEvidenceV1) -> StandardPairInputBindV2:
    values = _pair_binding_values(timing)
    return StandardPairInputBindV2.model_validate(
        {**values, "binding_digest": canonical_digest(values)}
    )


def _pair_binding_values(timing: PairTimingEvidenceV1) -> dict[str, object]:
    return {
        "schema_version": 2,
        "algorithm_version": "standard-pair-input-bind-v2",
        "session_id": _SESSION,
        "manifest_digest": _MANIFEST,
        "synchronization_inventory_digest": _SYNC,
        "raw_integrity_attestation_digests": [canonical_digest({"raw-integrity": "synthetic"})],
        "timing": timing.model_dump(mode="json"),
    }


def _path_binding_values() -> dict[str, object]:
    return {
        "schema_version": 2,
        "algorithm_version": "standard-path-input-bind-v2",
        "session_id": "synthetic-session",
        "stream_id": "stream-0",
        "radio_id": "radio-0",
        "receiver_id": 0,
        "manifest_digest": canonical_digest({"manifest": "synthetic"}),
        "raw_integrity_attestation_digest": canonical_digest({"raw": "synthetic"}),
        "selected_stream_digest": canonical_digest({"stream": "synthetic"}),
        "compressed_chunk_closure_digest": canonical_digest({"compressed": "synthetic"}),
        "uncompressed_chunk_closure_digest": canonical_digest({"uncompressed": "synthetic"}),
        "synchronization_inventory_digest": _SYNC,
        "profile_revision_digest": canonical_digest({"profile": "synthetic"}),
        "capture_plan_digest": canonical_digest({"plan": "synthetic"}),
        "receiver_settings_digest": canonical_digest({"settings": "synthetic"}),
        "science_configuration_digest": canonical_digest({"config": "synthetic"}),
        "science_implementation_digest": canonical_digest({"implementation": "synthetic"}),
        "capture_lineage_resolution": "legacy_unresolved",
        "physical_receiver_id": None,
        "hardware_epoch_id": None,
        "tuned_center_frequency_hz": 1_709_687_500,
        "sample_rate_hz": 2_500_000,
        "declared_sample_count": 150_000_000,
        "timing": _timing(10_000_000_000).model_dump(mode="json"),
        "frequency_reference": {"reference": "uncalibrated_prior"},
    }


def _polynomial(label: str, *, degree: int) -> PolynomialTrajectory:
    return PolynomialTrajectory(
        trajectory_id=canonical_digest({"trajectory": label}),
        method=PilotMethod.GLRT64,
        polynomial_degree=degree,
        reference_time_s=2.0,
        coefficients_hz=tuple(float(index + 1) for index in range(degree + 1)),
        start_s=0.0,
        end_s=4.0,
        observation_ids=tuple(
            canonical_digest({"trajectory": label, "point": index}) for index in range(6)
        ),
        point_count=6,
        residual_rms_hz=100.0,
        bic=10.0,
        high_gate=0.1,
        em_iterations=2,
    )


class _DualReader:
    sample_rate_hz = 1_000
    center_frequency_hz = 1_000_000
    receiver_ids = (0, 1)
    sample_count = 4_000

    def iter_blocks(self, *, block_samples: int) -> Iterator[IqBlock]:
        interval = NanosecondIntervalV1(lower_ns=0, upper_ns=0)
        for start in range(0, self.sample_count, block_samples):
            count = min(block_samples, self.sample_count - start)
            samples = np.empty((count, 2, 2), dtype="<i2")
            samples[:, 0, 0] = 100
            samples[:, 0, 1] = -50
            samples[:, 1, 0] = 1_000
            samples[:, 1, 1] = -500
            yield IqBlock(
                samples=np.ascontiguousarray(samples),
                metadata=IqBlockMetadataV1(
                    radio_id="radio-0",
                    receiver_ids=(0, 1),
                    sample_count=count,
                    session_sample_start=start,
                    host_request_utc_ns=interval,
                    host_request_monotonic_ns=interval,
                ),
            )
