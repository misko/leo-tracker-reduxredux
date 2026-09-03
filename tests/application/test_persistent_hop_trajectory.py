from __future__ import annotations

from leo.application.persistent_hop_trajectory import (
    PersistentHopTrajectoryProjectionConfig,
    project_fractional_persistent_hop_candidates,
)
from leo.scanner.fake_persistent_hop import FakePersistentHopRadio
from leo.scanner.persistent_hop import (
    PersistentHopUtcTimingAuthorityV1,
    compile_persistent_hop_plan_v1,
)
from leo.scanner.persistent_hop_products import (
    PersistentHopAnalysisChunkV2,
    PersistentHopAnalysisConfigurationV2,
    PersistentHopCandidateV2,
    PersistentHopProbeMetricV2,
)
from leo.storage.persistent_hop import PersistentHopIqStore


def _one_visit_manifest(tmp_path):  # type: ignore[no-untyped-def]
    plan = compile_persistent_hop_plan_v1(sample_rate_hz=2_500_000)
    radio = FakePersistentHopRadio()
    radio.open()
    session = radio.begin_session(plan, session_id="trajectory-projection")
    block = session.read_visit()
    session.request_cancel()
    receipt = session.finish()
    radio.close()
    timing = PersistentHopUtcTimingAuthorityV1.from_host_bracket(
        session_id=receipt.session_id,
        session_start_device_sample_counter=receipt.session_start_device_sample_counter,
        sample_rate_hz=plan.sample_rate_hz,
        begin_before_realtime_ns=1_800_000_000_000_000_000,
        begin_before_monotonic_ns=100_000_000_000,
        begin_after_realtime_ns=1_800_000_000_001_000_000,
        begin_after_monotonic_ns=100_001_000_000,
        terminal_realtime_ns=1_800_000_000_140_000_000,
        terminal_monotonic_ns=100_140_000_000,
    )
    store = PersistentHopIqStore(tmp_path)
    writer = store.begin(receipt.session_id, plan)
    writer.append(block)
    return writer.finish(receipt, timing=timing)


def _chunk(publication) -> PersistentHopAnalysisChunkV2:  # type: ignore[no-untyped-def]
    manifest = publication.manifest
    receipt = manifest.receipt
    visit = receipt.visits[0]
    configuration = PersistentHopAnalysisConfigurationV2()
    probes = []
    for probe_index in range(11):
        probe_start_ms = probe_index * configuration.probe_stride_ms
        probe_start_sample = probe_start_ms * receipt.plan.sample_rate_hz // 1_000
        for receiver_id in receipt.plan.receiver_ids:
            integer_counter = visit.valid_device_sample_counter + probe_start_sample + 100
            integer_session_sample = (
                integer_counter - receipt.session_start_device_sample_counter
            )
            candidate = PersistentHopCandidateV2(
                candidate_rank=0,
                integer_epoch_sample=100,
                fractional_epoch_offset_samples=0.25,
                integer_device_sample_counter=integer_counter,
                fractional_device_sample_counter=integer_counter + 0.25,
                integer_session_sample=integer_session_sample,
                fractional_session_sample=integer_session_sample + 0.25,
                fractional_time_s=(integer_session_sample + 0.25)
                / receipt.plan.sample_rate_hz,
                acquired_cfo_hz=1_000.0,
                integer_residual_cfo_hz=20.0,
                integer_tracking_cfo_hz=9_999.0,
                integer_exact_score=0.12,
                integer_control_score=0.10,
                integer_margin=0.02,
                passed_integer_margin_gate=False,
                fractional_residual_cfo_hz=18.0,
                fractional_tracking_cfo_hz=1_018.0,
                fractional_exact_score=0.15,
                fractional_control_score=0.10,
                fractional_margin=0.05,
                passed_fractional_margin_gate=True,
            )
            probes.append(
                PersistentHopProbeMetricV2(
                    visit_index=0,
                    sweep_index=0,
                    target_index=visit.target_index,
                    target=visit.target,
                    receiver_id=receiver_id,
                    probe_index=probe_index,
                    probe_start_ms=probe_start_ms,
                    candidate_count=1,
                    fractionally_scored_candidate_count=1,
                    fractional_candidates=(candidate,),
                    winning_candidate_rank=0,
                )
            )
    return PersistentHopAnalysisChunkV2(
        session_id=receipt.session_id,
        input_manifest_sha256=publication.manifest_sha256,
        configuration=configuration,
        sweep_index=0,
        first_visit_index=0,
        visit_count=1,
        scheduled_probe_count_per_receiver_visit=11,
        probes=tuple(probes),
    )


def test_projects_only_nonoverlapping_fractional_evidence_with_exact_support(tmp_path) -> None:
    publication = _one_visit_manifest(tmp_path)
    chunk = _chunk(publication)

    result = project_fractional_persistent_hop_candidates(
        publication.manifest,
        (chunk,),
        config=PersistentHopTrajectoryProjectionConfig(require_complete_capture=False),
    )

    assert result.integer_decision_values_consumed is False
    assert result.overlapping_probe_evidence_consumed is False
    assert result.input_probe_count == 22
    assert result.nonoverlapping_probe_count == 12
    assert result.projected_candidate_count == 12
    assert {item.probe_index for item in result.candidates} == {0, 2, 4, 6, 8, 10}
    assert {item.measured_cfo_hz for item in result.candidates} == {1_018.0}
    assert all(item.fractional_epoch_used for item in result.candidates)
    assert all(item.support_start_utc_ns < item.support_center_utc_ns for item in result.candidates)
    assert all(item.support_center_utc_ns < item.support_end_utc_ns for item in result.candidates)
    assert all(item.factorial_support_moments_s[0:2] == (1.0, 0.0) for item in result.candidates)

    for receiver_id in (0, 1):
        rows = sorted(
            (item for item in result.candidates if item.receiver_id == receiver_id),
            key=lambda item: item.source_sample_start,
        )
        assert all(
            right.source_sample_start >= left.source_sample_end
            for left, right in zip(rows, rows[1:], strict=False)
        )
