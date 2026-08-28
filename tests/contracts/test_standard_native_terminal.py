from __future__ import annotations

import copy
from typing import Literal

import pytest
from pydantic import ValidationError

from leo.analysis.standard.native_reducers import (
    aggregate_sufficient_statistics,
    intersect_valid_utc_intervals,
    valid_utc_intervals,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import NativeQualityReceiverV2
from leo.contracts.standard_native_path_report import (
    NativePathScientificDispositionV1,
    StandardNativePathReportV3,
)
from leo.contracts.standard_native_terminal import (
    NativeTerminalPathEvidenceV2,
    StandardNativePairedReportV4,
    StandardNativePairedReportV5,
    StandardNativePairedReportV6,
    StandardNativeRadioReportV4,
    StandardNativeRadioReportV5,
    aggregate_native_probe_execution_accounting,
    aggregate_native_qam_statistics,
    aggregate_terminal_track_accounting,
    terminal_track_accounting,
)
from tests.analysis.test_standard_native_path_report import _build


def _terminal_path(report: StandardNativePathReportV3) -> NativeTerminalPathEvidenceV2:
    source = report.source
    quality = NativeQualityReceiverV2(
        receiver_id=source.receiver_id,
        valid_sample_count=source.observed_sample_count,
        energy_sum_ci16_squared=2 * source.observed_sample_count,
        clipped_component_count=0,
        clipped_complex_sample_count=0,
        clipped_complex_fraction=0.0,
        constant_iq=True,
        minimum_i=1,
        maximum_i=1,
        minimum_q=1,
        maximum_q=1,
    )
    return NativeTerminalPathEvidenceV2(
        source=source,
        stage_outcome=("complete" if source.missing_sample_count == 0 else "partial_coverage"),
        path_report_product_digest=canonical_digest(report.model_dump(mode="json")),
        full_capture_glrt20ms_product_digest=(report.products.full_capture_glrt20ms_product_digest),
        path_report=report,
        clipping_abs_threshold=32_767,
        uncovered_region_count=int(bool(source.missing_sample_count)),
        quality=quality,
        terminal_opportunities=report.schedule_execution.accounting,
        qam_statistics=report.qam_statistics,
        terminal_tracks=terminal_track_accounting(report),
        valid_utc_intervals=valid_utc_intervals(source),
    )


def _radio_report(
    *,
    stream_id: str,
    radio_id: str,
    gapped: bool,
    sample_rate_hz: int = 3_000_000,
) -> StandardNativeRadioReportV4:
    statuses: tuple[Literal["complete", "no_result", "insufficient"], ...] = (
        (("complete", "no_result") if gapped else ("complete", "no_result", "complete"))
        if sample_rate_hz == 3_000_000
        else (("no_result", "no_result") if gapped else ("no_result",) * 3)
    )
    paths = tuple(
        _terminal_path(
            _build(
                gapped=gapped,
                detection_statuses=statuses,
                stream_id=stream_id,
                radio_id=radio_id,
                receiver_id=receiver_id,
                sample_rate_hz=sample_rate_hz,
                include_tracks=sample_rate_hz == 3_000_000,
            )
        )
        for receiver_id in (0, 1)
    )
    intervals = intersect_valid_utc_intervals(
        paths[0].valid_utc_intervals,
        paths[1].valid_utc_intervals,
    )
    scientific_disposition = (
        NativePathScientificDispositionV1.CANDIDATE
        if any(
            item.path_report.scientific_disposition is NativePathScientificDispositionV1.CANDIDATE
            for item in paths
        )
        else NativePathScientificDispositionV1.NO_CANDIDATE
    )
    values = {
        "schema_version": 4,
        "algorithm_version": "standard-native-radio-report-v4",
        "session_id": paths[0].source.session_id,
        "stream_id": stream_id,
        "radio_id": radio_id,
        "manifest_digest": paths[0].source.manifest_digest,
        "synchronization_inventory_digest": (paths[0].source.synchronization_inventory_digest),
        "sample_rate_hz": paths[0].source.sample_rate_hz,
        "status": "partial_coverage" if gapped else "complete",
        "reason": "terminal test radio report",
        "paths": tuple(item.model_dump(mode="json") for item in paths),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.quality for item in paths)
        ).model_dump(mode="json"),
        "aggregate_terminal_opportunities": aggregate_native_probe_execution_accounting(
            tuple(item.terminal_opportunities for item in paths)
        ).model_dump(mode="json"),
        "aggregate_qam_statistics": aggregate_native_qam_statistics(
            tuple(item.qam_statistics for item in paths)
        ).model_dump(mode="json"),
        "aggregate_terminal_tracks": aggregate_terminal_track_accounting(
            tuple(item.terminal_tracks for item in paths)
        ).model_dump(mode="json"),
        "scientific_disposition": scientific_disposition.value,
        "scientific_reason": "candidate-only terminal test evidence",
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "cross_path_association_permitted": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    return StandardNativeRadioReportV4.model_validate(
        {**values, "report_digest": canonical_digest(values)}
    )


def test_terminal_radio_preserves_segment_tracks_and_merges_qam_sufficient_statistics() -> None:
    report = _radio_report(stream_id="stream-0", radio_id="radio-0", gapped=True)

    assert report.aggregate_qam_statistics.qam_result_count == 2
    assert report.aggregate_qam_statistics.symbol_count == 4_800
    assert report.aggregate_qam_statistics.hard_symbol_accuracy == 1
    assert report.aggregate_terminal_opportunities.analyzed_count == 4
    assert report.aggregate_terminal_opportunities.gap_excluded_count == 2
    assert report.aggregate_terminal_tracks.segment_count == 4
    assert report.aggregate_terminal_tracks.returned_trajectory_count == 2
    assert report.scientific_disposition is NativePathScientificDispositionV1.CANDIDATE
    assert report.cross_path_association_permitted is False
    assert all(
        path.path_report.cross_segment_association_permitted is False for path in report.paths
    )
    assert StandardNativeRadioReportV4.model_validate(report.model_dump(mode="json")) == report


def test_terminal_paired_report_aggregates_counts_without_cross_radio_association() -> None:
    radios = (
        _radio_report(stream_id="stream-0", radio_id="radio-0", gapped=False),
        _radio_report(stream_id="stream-1", radio_id="radio-1", gapped=True),
    )
    intervals = intersect_valid_utc_intervals(
        radios[0].valid_utc_intervals,
        radios[1].valid_utc_intervals,
    )
    values = {
        "schema_version": 4,
        "algorithm_version": "standard-native-paired-report-v4",
        "session_id": radios[0].session_id,
        "manifest_digest": radios[0].manifest_digest,
        "synchronization_inventory_digest": radios[0].synchronization_inventory_digest,
        "pair_input_binding_digest": canonical_digest({"pair": "terminal"}),
        "sample_rate_hz": radios[0].sample_rate_hz,
        "status": "partial_coverage",
        "reason": "terminal test paired report",
        "radios": tuple(item.model_dump(mode="json") for item in radios),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.aggregate_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_opportunities": aggregate_native_probe_execution_accounting(
            tuple(item.aggregate_terminal_opportunities for item in radios)
        ).model_dump(mode="json"),
        "aggregate_qam_statistics": aggregate_native_qam_statistics(
            tuple(item.aggregate_qam_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_tracks": aggregate_terminal_track_accounting(
            tuple(item.aggregate_terminal_tracks for item in radios)
        ).model_dump(mode="json"),
        "scientific_disposition": "candidate",
        "scientific_reason": "candidate-only terminal test evidence",
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "phase_coherent": False,
        "cross_radio_association_permitted": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    paired = StandardNativePairedReportV4.model_validate(
        {**values, "report_digest": canonical_digest(values)}
    )

    assert paired.aggregate_qam_statistics.qam_result_count == 6
    assert paired.aggregate_terminal_tracks.returned_trajectory_count == 4
    assert paired.aggregate_statistics.receiver_path_count == 4
    assert paired.cross_radio_association_permitted is False
    assert paired.phase_coherent is False


def test_terminal_paired_v5_preserves_unequal_native_rates_without_resampling() -> None:
    left = _radio_report(
        stream_id="stream-0", radio_id="radio-0", gapped=False, sample_rate_hz=2_500_000
    )
    right = _radio_report(
        stream_id="stream-1", radio_id="radio-1", gapped=True, sample_rate_hz=5_000_000
    )
    radios = (left, right)
    intervals = intersect_valid_utc_intervals(
        left.valid_utc_intervals,
        right.valid_utc_intervals,
    )
    values = {
        "schema_version": 5,
        "algorithm_version": "standard-native-paired-report-v5",
        "session_id": left.session_id,
        "manifest_digest": left.manifest_digest,
        "synchronization_inventory_digest": left.synchronization_inventory_digest,
        "pair_input_binding_digest": canonical_digest({"pair": "mixed-terminal"}),
        "radio_sample_rates_hz": (left.sample_rate_hz, right.sample_rate_hz),
        "status": "partial_coverage",
        "reason": "mixed terminal test paired report",
        "radios": tuple(item.model_dump(mode="json") for item in radios),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.aggregate_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_opportunities": aggregate_native_probe_execution_accounting(
            tuple(item.aggregate_terminal_opportunities for item in radios)
        ).model_dump(mode="json"),
        "aggregate_qam_statistics": aggregate_native_qam_statistics(
            tuple(item.aggregate_qam_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_tracks": aggregate_terminal_track_accounting(
            tuple(item.aggregate_terminal_tracks for item in radios)
        ).model_dump(mode="json"),
        "scientific_disposition": "no_candidate",
        "scientific_reason": "candidate-only terminal test evidence",
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "phase_coherent": False,
        "cross_radio_association_permitted": False,
        "resampling_permitted": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    paired = StandardNativePairedReportV5.model_validate(
        {**values, "report_digest": canonical_digest(values)}
    )

    assert paired.radio_sample_rates_hz == (2_500_000, 5_000_000)
    assert paired.resampling_permitted is False
    changed = paired.model_dump(mode="json")
    changed["radio_sample_rates_hz"] = [5_000_000, 2_500_000]
    changed["report_digest"] = canonical_digest(
        {key: value for key, value in changed.items() if key != "report_digest"}
    )
    with pytest.raises(ValidationError, match="rate inventory"):
        StandardNativePairedReportV5.model_validate(changed)


def test_terminal_v5_v6_preserve_single_rx_production_authority() -> None:
    dual = _radio_report(
        stream_id="stream-0",
        radio_id="radio-0",
        gapped=False,
        sample_rate_hz=2_500_000,
    )
    path = dual.paths[1]
    radio_values = {
        **dual.model_dump(mode="json", exclude={"report_digest"}),
        "schema_version": 5,
        "algorithm_version": "standard-native-radio-report-v5",
        "paths": (path.model_dump(mode="json"),),
        "aggregate_statistics": aggregate_sufficient_statistics((path.quality,)).model_dump(
            mode="json"
        ),
        "aggregate_terminal_opportunities": path.terminal_opportunities.model_dump(mode="json"),
        "aggregate_qam_statistics": path.qam_statistics.model_dump(mode="json"),
        "aggregate_terminal_tracks": path.terminal_tracks.model_dump(mode="json"),
        "valid_utc_intervals": tuple(
            item.model_dump(mode="json") for item in path.valid_utc_intervals
        ),
    }
    single = StandardNativeRadioReportV5.model_validate(
        {**radio_values, "report_digest": canonical_digest(radio_values)}
    )
    assert tuple(item.source.receiver_id for item in single.paths) == (1,)
    assert single.aggregate_statistics.receiver_path_count == 1

    peer = _radio_report(
        stream_id="stream-1",
        radio_id="radio-1",
        gapped=False,
        sample_rate_hz=5_000_000,
    )
    radios = (single, peer)
    intervals = intersect_valid_utc_intervals(
        single.valid_utc_intervals,
        peer.valid_utc_intervals,
    )
    paired_values = {
        "schema_version": 6,
        "algorithm_version": "standard-native-paired-report-v6",
        "session_id": single.session_id,
        "manifest_digest": single.manifest_digest,
        "synchronization_inventory_digest": single.synchronization_inventory_digest,
        "pair_input_binding_digest": canonical_digest({"pair": "production-terminal"}),
        "radio_sample_rates_hz": (single.sample_rate_hz, peer.sample_rate_hz),
        "status": "complete",
        "reason": "production terminal test paired report",
        "radios": tuple(item.model_dump(mode="json") for item in radios),
        "aggregate_statistics": aggregate_sufficient_statistics(
            tuple(item.aggregate_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_opportunities": aggregate_native_probe_execution_accounting(
            tuple(item.aggregate_terminal_opportunities for item in radios)
        ).model_dump(mode="json"),
        "aggregate_qam_statistics": aggregate_native_qam_statistics(
            tuple(item.aggregate_qam_statistics for item in radios)
        ).model_dump(mode="json"),
        "aggregate_terminal_tracks": aggregate_terminal_track_accounting(
            tuple(item.aggregate_terminal_tracks for item in radios)
        ).model_dump(mode="json"),
        "scientific_disposition": "no_candidate",
        "scientific_reason": "candidate-only production terminal test evidence",
        "valid_utc_intervals": tuple(item.model_dump(mode="json") for item in intervals),
        "native_evidence_only": True,
        "current_eligible": False,
        "phase_coherent": False,
        "cross_radio_association_permitted": False,
        "resampling_permitted": False,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
    }
    paired = StandardNativePairedReportV6.model_validate(
        {**paired_values, "report_digest": canonical_digest(paired_values)}
    )
    assert paired.aggregate_statistics.receiver_path_count == 3
    assert tuple(len(item.paths) for item in paired.radios) == (1, 2)


def test_terminal_path_rejects_changed_report_digest_and_qam_aggregate_tamper() -> None:
    report = _radio_report(stream_id="stream-0", radio_id="radio-0", gapped=False)
    path_values = report.paths[0].model_dump(mode="json")
    path_values["path_report_product_digest"] = canonical_digest({"tampered": True})
    with pytest.raises(ValidationError, match="lineage"):
        NativeTerminalPathEvidenceV2.model_validate(path_values)

    radio_values = copy.deepcopy(report.model_dump(mode="json"))
    radio_values["aggregate_qam_statistics"]["correct_symbol_count"] -= 1
    radio_values["report_digest"] = canonical_digest(
        {key: value for key, value in radio_values.items() if key != "report_digest"}
    )
    with pytest.raises(ValidationError, match="derived metrics|sufficient statistics"):
        StandardNativeRadioReportV4.model_validate(radio_values)
