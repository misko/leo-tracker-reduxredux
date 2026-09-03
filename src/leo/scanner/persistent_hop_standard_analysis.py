"""Pure bounded analysis of one persistent-hop sweep at a time."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from leo.scanner.detector import (
    DwellGlrt64Analysis,
    Glrt64CandidateResponse,
    analyze_glrt64_dwell,
)
from leo.scanner.persistent_hop_analysis import (
    PersistentHopAnalysisSource,
    PersistentHopAnalysisVisitInput,
    PersistentHopGlrt64Configuration,
)
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV1,
    PersistentHopAnalysisChunkV2,
    PersistentHopAnalysisConfigurationV1,
    PersistentHopAnalysisConfigurationV2,
    PersistentHopBestCandidateV1,
    PersistentHopCandidateV2,
    PersistentHopProbeMetricV1,
    PersistentHopProbeMetricV2,
)


def persistent_hop_product_configuration(
    configuration: PersistentHopGlrt64Configuration,
) -> PersistentHopAnalysisConfigurationV1:
    return PersistentHopAnalysisConfigurationV1.model_validate(
        {
            "probe_ms": configuration.probe_ms,
            "probe_stride_ms": configuration.probe_stride_ms,
            "glrt64_margin_gate": configuration.glrt64_margin_gate,
            "maximum_acquisition_candidates": configuration.maximum_acquisition_candidates,
        }
    )


def persistent_hop_fractional_product_configuration(
    configuration: PersistentHopGlrt64Configuration,
) -> PersistentHopAnalysisConfigurationV2:
    return PersistentHopAnalysisConfigurationV2.model_validate(
        {
            "probe_ms": configuration.probe_ms,
            "probe_stride_ms": configuration.probe_stride_ms,
            "glrt64_margin_gate": configuration.glrt64_margin_gate,
            "maximum_acquisition_candidates": configuration.maximum_acquisition_candidates,
        }
    )


def analyze_persistent_hop_sweep(
    source: PersistentHopAnalysisSource,
    sweep_index: int,
    *,
    configuration: PersistentHopGlrt64Configuration | None = None,
    maximum_workers: int = 1,
) -> PersistentHopAnalysisChunkV1:
    """Analyze one at-most-eight-visit sweep without retaining its IQ."""

    selected = configuration or PersistentHopGlrt64Configuration(source.plan)
    if selected.plan != source.plan:
        raise ValueError("persistent-hop analysis configuration disagrees with source")
    if not 1 <= maximum_workers <= 2:
        raise ValueError("persistent-hop analysis worker count must lie in 1..2")
    spans = tuple(item for item in source.visits if item.sweep_index == sweep_index)
    if not spans:
        raise ValueError("persistent-hop analysis sweep does not exist")
    if tuple(item.visit_index for item in spans) != tuple(
        range(spans[0].visit_index, spans[0].visit_index + len(spans))
    ):
        raise ValueError("persistent-hop analysis sweep visits are not contiguous")

    if maximum_workers == 1:
        analyses = tuple(
            source.analyze_glrt64_visit(
                span.visit_index,
                configuration=selected,
            )
            for span in spans
        )
    else:
        visits = tuple(source.read_visit(span.visit_index) for span in spans)
        with ThreadPoolExecutor(
            max_workers=maximum_workers,
            thread_name_prefix="leo-hop-glrt",
        ) as executor:
            analyses = tuple(
                executor.map(
                    lambda visit: _analyze_loaded_visit(visit, selected),
                    visits,
                )
            )

    rows: list[PersistentHopProbeMetricV1] = []
    session_counter_start = source.receipt.session_start_device_sample_counter
    for span, analysis in zip(spans, analyses, strict=True):
        expected_probe_rows = selected.scheduled_probe_count * len(selected.receiver_ids)
        if len(analysis.probes) != expected_probe_rows:
            raise ValueError("persistent-hop dwell analyzer returned incomplete probe coverage")
        for probe in analysis.probes:
            best_response = max(
                probe.candidates,
                key=lambda item: (item.margin, -item.candidate_rank),
                default=None,
            )
            best: PersistentHopBestCandidateV1 | None = None
            if best_response is not None:
                probe_start_sample = probe.probe_start_ms * source.sample_rate_hz // 1_000
                integer_counter = (
                    span.valid_device_sample_counter
                    + probe_start_sample
                    + best_response.epoch_sample
                )
                integer_session_sample = integer_counter - session_counter_start
                fractional_offset = best_response.fractional_epoch_offset_samples
                effective_counter = integer_counter + (fractional_offset or 0.0)
                effective_session_sample = integer_session_sample + (fractional_offset or 0.0)
                best = PersistentHopBestCandidateV1(
                    candidate_rank=best_response.candidate_rank,
                    integer_epoch_sample=best_response.epoch_sample,
                    fractional_epoch_status=best_response.fractional_epoch_status,
                    fractional_epoch_offset_samples=fractional_offset,
                    integer_device_sample_counter=integer_counter,
                    effective_device_sample_counter=effective_counter,
                    integer_session_sample=integer_session_sample,
                    effective_session_sample=effective_session_sample,
                    effective_time_s=effective_session_sample / source.sample_rate_hz,
                    acquired_cfo_hz=best_response.acquired_cfo_hz,
                    residual_cfo_hz=best_response.residual_cfo_hz,
                    tracking_cfo_hz=best_response.tracking_cfo_hz,
                    exact_score=best_response.exact_score,
                    control_score=best_response.control_score,
                    margin=best_response.margin,
                    passed_margin_gate=best_response.passed_margin_gate,
                )
            rows.append(
                PersistentHopProbeMetricV1(
                    visit_index=span.visit_index,
                    sweep_index=span.sweep_index,
                    target_index=span.target_index,
                    target=span.target,
                    receiver_id=probe.receiver_id,
                    probe_index=probe.probe_index,
                    probe_start_ms=probe.probe_start_ms,
                    candidate_count=len(probe.candidates),
                    best=best,
                )
            )

    return PersistentHopAnalysisChunkV1(
        session_id=source.session_id,
        input_manifest_sha256=source.input_manifest_sha256,
        configuration=persistent_hop_product_configuration(selected),
        sweep_index=sweep_index,
        first_visit_index=spans[0].visit_index,
        visit_count=len(spans),
        scheduled_probe_count_per_receiver_visit=selected.scheduled_probe_count,
        receiver_ids=selected.receiver_ids,
        probes=tuple(rows),
    )


def _analyze_loaded_visit(
    visit: PersistentHopAnalysisVisitInput,
    configuration: PersistentHopGlrt64Configuration,
) -> DwellGlrt64Analysis:
    return analyze_glrt64_dwell(
        visit.complex_samples(),
        configuration,
        edge=visit.span.target.edge,
    )


def analyze_persistent_hop_sweep_v2(
    source: PersistentHopAnalysisSource,
    sweep_index: int,
    *,
    configuration: PersistentHopGlrt64Configuration | None = None,
    maximum_workers: int = 1,
) -> PersistentHopAnalysisChunkV2:
    """Analyze one sweep with fractional GLRT scores as the only decision values."""

    selected = configuration or PersistentHopGlrt64Configuration(source.plan)
    if selected.plan != source.plan:
        raise ValueError("persistent-hop V2 analysis configuration disagrees with source")
    if not 1 <= maximum_workers <= 2:
        raise ValueError("persistent-hop V2 worker count must lie in 1..2")
    spans = tuple(item for item in source.visits if item.sweep_index == sweep_index)
    if not spans:
        raise ValueError("persistent-hop V2 analysis sweep does not exist")
    if tuple(item.visit_index for item in spans) != tuple(
        range(spans[0].visit_index, spans[0].visit_index + len(spans))
    ):
        raise ValueError("persistent-hop V2 sweep visits are not contiguous")

    if maximum_workers == 1:
        analyses = tuple(
            source.analyze_glrt64_visit(span.visit_index, configuration=selected) for span in spans
        )
    else:
        visits = tuple(source.read_visit(span.visit_index) for span in spans)
        with ThreadPoolExecutor(
            max_workers=maximum_workers,
            thread_name_prefix="leo-hop-fractional-glrt",
        ) as executor:
            analyses = tuple(
                executor.map(lambda visit: _analyze_loaded_visit(visit, selected), visits)
            )

    rows: list[PersistentHopProbeMetricV2] = []
    session_counter_start = source.receipt.session_start_device_sample_counter
    for span, analysis in zip(spans, analyses, strict=True):
        expected_probe_rows = selected.scheduled_probe_count * len(selected.receiver_ids)
        if len(analysis.probes) != expected_probe_rows:
            raise ValueError("persistent-hop V2 dwell analyzer returned incomplete coverage")
        for probe in analysis.probes:
            fractionally_scored = tuple(
                item
                for item in probe.candidates
                if item.fractional_epoch_status == "complete"
                and item.fractional_epoch_offset_samples is not None
                and item.fractional_residual_cfo_hz is not None
                and item.fractional_tracking_cfo_hz is not None
                and item.fractional_exact_score is not None
                and item.fractional_control_score is not None
                and item.fractional_margin is not None
            )
            probe_start_sample = probe.probe_start_ms * source.sample_rate_hz // 1_000
            candidates = tuple(
                _persistent_hop_fractional_candidate(
                    item,
                    span_device_sample_counter=span.valid_device_sample_counter,
                    probe_start_sample=probe_start_sample,
                    session_counter_start=session_counter_start,
                    sample_rate_hz=source.sample_rate_hz,
                    margin_gate=selected.glrt64_margin_gate,
                )
                for item in fractionally_scored
            )
            winner = max(
                candidates,
                key=lambda item: (item.fractional_margin, -item.candidate_rank),
                default=None,
            )
            rows.append(
                PersistentHopProbeMetricV2(
                    visit_index=span.visit_index,
                    sweep_index=span.sweep_index,
                    target_index=span.target_index,
                    target=span.target,
                    receiver_id=probe.receiver_id,
                    probe_index=probe.probe_index,
                    probe_start_ms=probe.probe_start_ms,
                    candidate_count=len(probe.candidates),
                    fractionally_scored_candidate_count=len(fractionally_scored),
                    fractional_candidates=candidates,
                    winning_candidate_rank=(None if winner is None else winner.candidate_rank),
                )
            )

    return PersistentHopAnalysisChunkV2(
        session_id=source.session_id,
        input_manifest_sha256=source.input_manifest_sha256,
        configuration=persistent_hop_fractional_product_configuration(selected),
        sweep_index=sweep_index,
        first_visit_index=spans[0].visit_index,
        visit_count=len(spans),
        scheduled_probe_count_per_receiver_visit=selected.scheduled_probe_count,
        receiver_ids=selected.receiver_ids,
        probes=tuple(rows),
    )


def _persistent_hop_fractional_candidate(
    response: Glrt64CandidateResponse,
    *,
    span_device_sample_counter: int,
    probe_start_sample: int,
    session_counter_start: int,
    sample_rate_hz: int,
    margin_gate: float,
) -> PersistentHopCandidateV2:
    assert response.fractional_epoch_status == "complete"
    assert response.fractional_epoch_offset_samples is not None
    assert response.fractional_residual_cfo_hz is not None
    assert response.fractional_tracking_cfo_hz is not None
    assert response.fractional_exact_score is not None
    assert response.fractional_control_score is not None
    assert response.fractional_margin is not None
    integer_counter = span_device_sample_counter + probe_start_sample + response.epoch_sample
    integer_session_sample = integer_counter - session_counter_start
    offset = response.fractional_epoch_offset_samples
    fractional_counter = integer_counter + offset
    fractional_session_sample = integer_session_sample + offset
    return PersistentHopCandidateV2(
        candidate_rank=response.candidate_rank,
        integer_epoch_sample=response.epoch_sample,
        fractional_epoch_offset_samples=offset,
        integer_device_sample_counter=integer_counter,
        fractional_device_sample_counter=fractional_counter,
        integer_session_sample=integer_session_sample,
        fractional_session_sample=fractional_session_sample,
        fractional_time_s=fractional_session_sample / sample_rate_hz,
        acquired_cfo_hz=response.acquired_cfo_hz,
        integer_residual_cfo_hz=response.residual_cfo_hz,
        integer_tracking_cfo_hz=response.tracking_cfo_hz,
        integer_exact_score=response.exact_score,
        integer_control_score=response.control_score,
        integer_margin=response.margin,
        passed_integer_margin_gate=response.margin >= margin_gate,
        fractional_residual_cfo_hz=response.fractional_residual_cfo_hz,
        fractional_tracking_cfo_hz=response.fractional_tracking_cfo_hz,
        fractional_exact_score=response.fractional_exact_score,
        fractional_control_score=response.fractional_control_score,
        fractional_margin=response.fractional_margin,
        passed_fractional_margin_gate=response.fractional_margin >= margin_gate,
    )
