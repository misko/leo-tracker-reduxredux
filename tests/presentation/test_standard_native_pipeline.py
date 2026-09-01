from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.pipeline import ScopeIdentityV1
from leo.presentation.standard_native_pipeline import (
    StandardNativeAnalysisSelectionV1,
    StandardNativeEligibilityV3,
    StandardNativeEligibilityV4,
    StandardNativeEligibilityV5,
    StandardNativeEligibilityV6,
    StandardNativeMixedLegV4,
    StandardNativePipelineReleaseV3,
    StandardNativeProductionLegV5,
    StandardNativeProductionLegV6,
    StandardNativeSubjectHierarchyV3,
    StandardNativeSubjectHierarchyV7,
    StandardNativeSubjectSummaryV3,
    StandardNativeSubjectSummaryV7,
    StandardNativeTerminalSummaryV3,
    StandardNativeWaterfallTileV3,
)
from leo.presentation.standard_pipeline import (
    StandardReceiverPathRefV2,
    StandardReuseSummaryV2,
    StandardSubjectKindV2,
)
from tests.contracts.test_standard_native_terminal import _radio_report

_RELEASE = "7" * 40


def _eligibility() -> StandardNativeEligibilityV3:
    return StandardNativeEligibilityV3(
        capture_state="degraded",
        capture_committed=False,
        profile_revision_digest=canonical_digest({"profile": "3m"}),
        sample_rate_hz=3_000_000,
        pipeline_definition_id=canonical_digest({"definition": "native"}),
        promotion_authority_digest=canonical_digest({"authority": "current"}),
        reason=(
            "Promoted reviewed V3 Standard-native capture is Current with partial validity coverage"
        ),
    )


def _release() -> StandardNativePipelineReleaseV3:
    eligibility = _eligibility()
    return StandardNativePipelineReleaseV3(
        authoritative_pipeline_release_id=_RELEASE,
        source_revision=_RELEASE,
        pipeline_definition_id=eligibility.pipeline_definition_id,
        graph_digest=canonical_digest({"graph": "native"}),
        configuration_digest=canonical_digest({"configuration": "native"}),
        environment_digest=canonical_digest({"environment": "native"}),
    )


def _radio_summary() -> StandardNativeSubjectSummaryV3:
    report = _radio_report(stream_id="stream-0", radio_id="radio-0", gapped=True)
    expected = sum(item.source.logical_sample_count for item in report.paths)
    valid = report.aggregate_statistics.valid_complex_sample_count
    terminal = StandardNativeTerminalSummaryV3(
        expected_complex_sample_count=expected,
        valid_complex_sample_count=valid,
        missing_complex_sample_count=expected - valid,
        coverage_fraction=valid / expected,
        coverage_status=report.status,
        sufficient_statistics=report.aggregate_statistics,
        terminal_opportunities=report.aggregate_terminal_opportunities,
        qam_statistics=report.aggregate_qam_statistics,
        terminal_tracks=report.aggregate_terminal_tracks,
        scientific_disposition=report.scientific_disposition,
        valid_utc_intervals=report.valid_utc_intervals,
    )
    refs = tuple(
        StandardReceiverPathRefV2(
            subject_id=f"path:radio-0:rx{path.source.receiver_id}",
            path_id=f"radio-0:rx{path.source.receiver_id}",
            radio_id="radio-0",
            radio_label="Radio0",
            receiver_id=path.source.receiver_id,
            receiver_label=f"RX{path.source.receiver_id}",
            scope=(
                scope := ScopeIdentityV1.receiver_path(
                    session_id=report.session_id,
                    stream_id=report.stream_id,
                    receiver_id=path.source.receiver_id,
                )
            ),
            scope_digest=scope.canonical_digest.removeprefix("sha256:"),
        )
        for path in report.paths
    )
    release = _release()
    return StandardNativeSubjectSummaryV3(
        subject_id="radio:stream-0",
        session_id=report.session_id,
        subject_kind=StandardSubjectKindV2.RADIO,
        label="Radio0",
        derived=True,
        receiver_paths=refs,
        expected_path_count=2,
        completed_path_count=2,
        child_subject_ids=tuple(item.subject_id for item in refs),
        coverage_status="partial_coverage",
        scientific_disposition=report.scientific_disposition,
        pipeline_release=release,
        desired_pipeline_release_id=_RELEASE,
        reuse=StandardReuseSummaryV2(
            computed_stage_count=1,
            reused_stage_count=0,
            recompute_stage_count=0,
            reason="Rendered for this run",
        ),
        eligibility=_eligibility(),
        terminal=terminal,
    )


def test_degraded_promoted_native_subject_is_current_with_partial_coverage() -> None:
    row = _radio_summary()
    hierarchy = StandardNativeSubjectHierarchyV3(
        session_id=row.session_id,
        eligibility=row.eligibility,
        generated_at="2026-08-26T00:00:00Z",
        rows=(row,),
    )

    assert hierarchy.schema_version == 3
    assert row.state.value == "current"
    assert row.ordinary_current is True
    assert row.coverage_status == "partial_coverage"
    assert row.scientific_disposition == row.terminal.scientific_disposition
    assert row.terminal.reducer_uses_sufficient_statistics is True
    assert row.terminal.cross_gap_operation_permitted is False


def test_native_subject_rejects_coverage_or_science_relabeling() -> None:
    document = _radio_summary().model_dump(mode="json")
    document["coverage_status"] = "complete"
    with pytest.raises(ValidationError, match="coverage differs"):
        StandardNativeSubjectSummaryV3.model_validate(document)

    document = _radio_summary().model_dump(mode="json")
    document["scientific_disposition"] = "no_candidate"
    with pytest.raises(ValidationError, match="science differs"):
        StandardNativeSubjectSummaryV3.model_validate(document)


def test_native_terminal_rejects_ratio_recomputation_or_simple_average_tamper() -> None:
    document = _radio_summary().terminal.model_dump(mode="json")
    document["coverage_fraction"] += 0.01
    with pytest.raises(ValidationError, match="coverage differs"):
        StandardNativeTerminalSummaryV3.model_validate(document)

    document = copy.deepcopy(_radio_summary().terminal.model_dump(mode="json"))
    document["qam_statistics"]["hard_symbol_accuracy"] = "0.5"
    with pytest.raises(ValidationError, match="derived metrics"):
        StandardNativeTerminalSummaryV3.model_validate(document)


def test_native_waterfall_keeps_missing_global_cell_explicitly_invalid() -> None:
    missing = StandardNativeWaterfallTileV3(
        receiver_path_id="radio-0:rx0",
        time_bin=4,
        time_start_s=4.0,
        time_stop_s=5.0,
        sample_start=12_000_000,
        sample_stop=15_000_000,
        transform_count=0,
        valid=False,
        power_dbfs=(None, None, None),
    )
    assert missing.valid is False
    assert missing.power_dbfs == (None, None, None)

    tampered = missing.model_dump(mode="json")
    tampered["power_dbfs"][1] = -42.0
    with pytest.raises(ValidationError, match="explicitly invalid"):
        StandardNativeWaterfallTileV3.model_validate(tampered)


def test_mixed_native_eligibility_preserves_each_rate_and_exact_rf_passband() -> None:
    legs = (
        StandardNativeMixedLegV4(
            stream_id="stream-0",
            radio_id="radio-0",
            profile_name="starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
            profile_revision_digest=canonical_digest({"profile": "2p5"}),
            starlink_channel=1,
            starlink_edge="lower",
            sample_rate_hz=2_500_000,
            rf_bandwidth_hz=2_500_000,
            tuned_center_frequency_hz=959_687_500,
            pilot_if_center_frequency_hz=959_687_500,
            channel_if_start_hz=955_000_000,
            channel_if_stop_hz=1_195_000_000,
            captured_if_start_hz=958_437_500,
            captured_if_stop_hz=960_937_500,
        ),
        StandardNativeMixedLegV4(
            stream_id="stream-1",
            radio_id="radio-1",
            profile_name="starlink-ch4-lower-5m-60s-mixed-device-axis-v4",
            profile_revision_digest=canonical_digest({"profile": "5"}),
            starlink_channel=1,
            starlink_edge="lower",
            sample_rate_hz=5_000_000,
            rf_bandwidth_hz=5_000_000,
            tuned_center_frequency_hz=959_687_500,
            pilot_if_center_frequency_hz=959_687_500,
            channel_if_start_hz=955_000_000,
            channel_if_stop_hz=1_195_000_000,
            captured_if_start_hz=957_187_500,
            captured_if_stop_hz=962_187_500,
        ),
    )
    eligibility = StandardNativeEligibilityV4(
        capture_state="degraded",
        capture_committed=False,
        dwell_class="mixed_2p5_5",
        legs=legs,
        pipeline_definition_id=canonical_digest({"definition": "mixed-native"}),
        promotion_authority_digest=canonical_digest({"authority": "mixed-current"}),
        reason=(
            "Promoted reviewed mixed Standard-native capture is Current with partial "
            "validity coverage"
        ),
    )

    assert tuple(item.sample_rate_hz for item in eligibility.legs) == (2_500_000, 5_000_000)
    assert all(item.rf_bandwidth_hz == item.sample_rate_hz for item in eligibility.legs)
    assert eligibility.resampled is False
    changed = eligibility.model_dump(mode="json")
    changed["legs"][1]["rf_bandwidth_hz"] = 2_500_000
    with pytest.raises(ValidationError, match="RF/passband"):
        StandardNativeEligibilityV4.model_validate(changed)


def test_production_native_eligibility_preserves_single_rx_and_tandem_authority() -> None:
    common = {
        "gain_controller_mode": "tandem_auto",
        "gain_controller_request_digest": canonical_digest({"controller": "auto"}),
        "starlink_channel": 1,
        "starlink_edge": "lower",
        "pilot_if_center_frequency_hz": 959_687_500,
        "channel_if_start_hz": 955_000_000,
        "channel_if_stop_hz": 1_195_000_000,
        "logical_sample_count": 100,
        "validity_inventory_digest": canonical_digest({"validity": True}),
        "timeline_digest": canonical_digest({"timeline": True}),
        "metadata_abi_version": 3,
    }
    legs = (
        StandardNativeProductionLegV5(
            stream_id="stream-0",
            radio_id="radio-0",
            profile_name="starlink-ch4-lower-2p5m-60s-mixed-device-axis-v4",
            profile_revision_digest=canonical_digest({"profile": "2p5"}),
            receiver_ids=(0, 1),
            sample_rate_hz=2_500_000,
            rf_bandwidth_hz=2_500_000,
            tuned_center_frequency_hz=959_687_500,
            captured_if_start_hz=958_437_500,
            captured_if_stop_hz=960_937_500,
            **common,
        ),
        StandardNativeProductionLegV5(
            stream_id="stream-1",
            radio_id="radio-1",
            profile_name="starlink-ch4-lower-20m-60s-rx1-production-v5",
            profile_revision_digest=canonical_digest({"profile": "20"}),
            receiver_ids=(1,),
            sample_rate_hz=20_000_000,
            rf_bandwidth_hz=20_000_000,
            tuned_center_frequency_hz=965_000_000,
            captured_if_start_hz=955_000_000,
            captured_if_stop_hz=975_000_000,
            **common,
        ),
    )
    eligibility = StandardNativeEligibilityV5(
        capture_state="committed",
        capture_committed=True,
        dwell_class="mixed_2p5_20",
        tuning_branch="same",
        legs=legs,
        scheduled_intent_digest=canonical_digest({"intent": True}),
        capture_plan_digest=canonical_digest({"plan": True}),
        capture_hardware_binding_digest=canonical_digest({"hardware": True}),
        pipeline_definition_id=canonical_digest({"definition": "production-native"}),
        promotion_authority_digest=canonical_digest({"authority": "production-current"}),
        reason="Promoted reviewed production Standard-native capture is Current",
    )

    assert eligibility.legs[1].receiver_ids == (1,)
    assert eligibility.legs[1].gain_controller_mode == "tandem_auto"
    assert eligibility.legs[1].metadata_abi_version == 3
    changed = eligibility.model_dump(mode="json")
    changed["legs"][1]["receiver_ids"] = [0, 1]
    with pytest.raises(ValidationError, match="receiver geometry"):
        StandardNativeEligibilityV5.model_validate(changed)


def test_selection_aware_hierarchy_preserves_full_capture_authority() -> None:
    common = {
        "gain_controller_mode": "tandem_hold",
        "gain_controller_request_digest": canonical_digest({"controller": "hold"}),
        "starlink_channel": 1,
        "starlink_edge": "lower",
        "pilot_if_center_frequency_hz": 959_687_500,
        "channel_if_start_hz": 955_000_000,
        "channel_if_stop_hz": 1_195_000_000,
        "logical_sample_count": 100,
        "validity_inventory_digest": canonical_digest({"validity": True}),
        "timeline_digest": canonical_digest({"timeline": True}),
        "metadata_abi_version": 3,
    }
    eligibility = StandardNativeEligibilityV6(
        capture_state="degraded",
        capture_committed=False,
        dwell_class="mixed_2p5_25",
        legs=(
            StandardNativeProductionLegV6(
                stream_id="stream-0",
                radio_id="radio-0",
                profile_name="direct-low",
                profile_revision_digest=canonical_digest({"profile": "2p5"}),
                receiver_ids=(0, 1),
                sample_rate_hz=2_500_000,
                rf_bandwidth_hz=2_500_000,
                tuned_center_frequency_hz=959_687_500,
                captured_if_start_hz=958_437_500,
                captured_if_stop_hz=960_937_500,
                **common,
            ),
            StandardNativeProductionLegV6(
                stream_id="stream-1",
                radio_id="radio-1",
                profile_name="direct-high",
                profile_revision_digest=canonical_digest({"profile": "25"}),
                receiver_ids=(0,),
                sample_rate_hz=25_000_000,
                rf_bandwidth_hz=25_000_000,
                tuned_center_frequency_hz=967_500_000,
                captured_if_start_hz=955_000_000,
                captured_if_stop_hz=980_000_000,
                **common,
            ),
        ),
        scheduled_intent_digest=canonical_digest({"intent": True}),
        capture_plan_digest=canonical_digest({"plan": True}),
        capture_hardware_binding_digest=canonical_digest({"hardware": True}),
        pipeline_definition_id=canonical_digest({"definition": "direct-native"}),
        promotion_authority_digest=canonical_digest({"authority": "direct-current"}),
        reason=(
            "Promoted reviewed production Standard-native capture is Current with partial "
            "validity coverage"
        ),
    )
    selection = StandardNativeAnalysisSelectionV1(
        analyzed_stream_ids=("stream-0",),
        omitted_stream_ids=("stream-1",),
    )
    row = StandardNativeSubjectSummaryV7.model_validate(
        {
            **_radio_summary().model_dump(mode="json"),
            "schema_version": 7,
            "eligibility": eligibility,
            "pipeline_release": _release().model_copy(
                update={"pipeline_definition_id": eligibility.pipeline_definition_id}
            ),
            "analysis_selection": selection,
        }
    )

    hierarchy = StandardNativeSubjectHierarchyV7(
        session_id=row.session_id,
        eligibility=eligibility,
        analysis_selection=selection,
        generated_at="2026-09-01T21:25:44Z",
        rows=(row,),
    )

    assert hierarchy.rows == (row,)
    assert hierarchy.analysis_selection.omitted_stream_ids == ("stream-1",)
    crossed = hierarchy.model_dump(mode="json")
    crossed["analysis_selection"]["analyzed_stream_ids"] = ["stream-1"]
    crossed["analysis_selection"]["omitted_stream_ids"] = ["stream-0"]
    crossed["rows"][0]["analysis_selection"] = crossed["analysis_selection"]
    with pytest.raises(ValidationError, match="authority is crossed"):
        StandardNativeSubjectHierarchyV7.model_validate(crossed)
