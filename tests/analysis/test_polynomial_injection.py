from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.polynomial_injection import (
    FrameCfoEvidence,
    evaluate_exact_qin_frames,
    fit_full_span_cubic,
    fixed_history_rate_estimates,
    inject_exact_qin,
    occupied_frame_mask,
    qin_frame_starts,
    truth_at_receiver_time,
)
from leo.analysis.research.polynomial_injection_protocol import (
    InjectionScenario,
    load_polynomial_injection_protocol,
)

PROJECT_ROOT = Path(__file__).parents[2]


def _protocol():
    policy = load_doppler_dataset_policy(
        PROJECT_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
    )
    return load_polynomial_injection_protocol(
        PROJECT_ROOT / "config/analysis/polynomial-phase-injection-protocol-v1.json",
        dataset_policy=policy,
        repository_root=PROJECT_ROOT,
    )


def _scenario(**changes: float | int | str) -> InjectionScenario:
    base = _protocol().scenarios[0]
    return replace(base, **changes)


def test_rounded_lattice_is_nonoverlapping_and_occupancy_is_exact() -> None:
    starts = qin_frame_starts(frame_count=1_500, sample_rate_hz=2_500_000)
    assert set(np.diff(starts).tolist()) == {3_333, 3_334}
    assert np.all(starts[:-1] + 3_333 <= starts[1:])
    assert starts[-1] + 3_333 <= 5_000_000

    first = occupied_frame_mask(frame_count=1_500, occupancy=0.35, seed=913_000)
    second = occupied_frame_mask(frame_count=1_500, occupancy=0.35, seed=913_000)
    assert int(np.sum(first)) == 525
    np.testing.assert_array_equal(first, second)


def test_clock_coordinate_truth_matches_numerical_phase_scaling() -> None:
    scenario = _scenario(
        rate_hz_s=4_000.0,
        acceleration_hz_s2=600.0,
        jerk_hz_s3=-240.0,
        sample_clock_offset_ppm=25.0,
        alias_change_hz=0.0,
        cfo_step_hz=0.0,
    )
    center = truth_at_receiver_time(
        scenario,
        1.2,
        carrier_origin_hz=100_000.0,
        reference_time_s=1.0,
        alias_change_time_s=1.0,
        cfo_step_time_s=1.1,
    )
    assert center.receiver_rate_hz_s != center.physical_rate_hz_s
    scale = 1.0 + 25e-6
    assert np.isclose(center.receiver_rate_hz_s, center.physical_rate_hz_s / scale**2)
    assert np.isclose(
        center.receiver_acceleration_hz_s2,
        center.physical_acceleration_hz_s2 / scale**3,
    )
    assert np.isclose(center.receiver_jerk_hz_s3, center.physical_jerk_hz_s3 / scale**4)


def test_exact_qin_injection_uses_public_split_frame_cfo() -> None:
    protocol = _protocol()
    background_binding = replace(protocol.backgrounds[0], sample_count=10_000)
    compact = replace(protocol, backgrounds=(background_binding,), frame_count=3)
    scenario = replace(
        protocol.scenarios[0],
        background_session_id=background_binding.session_id,
        rate_hz_s=0.0,
        acceleration_hz_s2=0.0,
        jerk_hz_s3=0.0,
        snr_db=20.0,
        frame_occupancy=1.0,
        alias_change_hz=0.0,
        cfo_step_hz=0.0,
        sample_clock_offset_ppm=0.0,
    )
    generator = np.random.default_rng(73)
    background = np.asarray(
        1e-3 * (generator.normal(size=10_000) + 1j * generator.normal(size=10_000)),
        dtype=np.complex64,
    )
    injected, occupancy, diagnostics = inject_exact_qin(background, scenario, compact)
    evidence = evaluate_exact_qin_frames(
        injected,
        occupancy,
        scenario,
        compact,
        absolute_span_start_sample=100,
    )

    assert diagnostics.occupied_frame_count == 3
    assert evidence[0].status == "incomplete_guard"
    assert all(item.training_supported for item in evidence[1:])
    assert all(item.even_canonical_cfo_hz is not None for item in evidence[1:])
    assert all(item.odd_canonical_cfo_hz is not None for item in evidence[1:])
    assert all(item.even_profile_margin is not None for item in evidence[1:])
    assert all(item.odd_profile_margin is not None for item in evidence[1:])


def _ideal_evidence(
    scenario: InjectionScenario,
    *,
    odd_offset_hz: float,
    frame_count: int = 1_000,
) -> tuple[FrameCfoEvidence, ...]:
    protocol = _protocol()
    output = []
    for frame_index in range(frame_count):
        time_s = (frame_index + 0.5) / 750.0
        truth = truth_at_receiver_time(
            scenario,
            time_s,
            carrier_origin_hz=protocol.carrier_origin_hz,
            reference_time_s=protocol.reference_time_s,
            alias_change_time_s=protocol.alias_change_time_s,
            cfo_step_time_s=protocol.cfo_step_time_s,
        )
        output.append(
            FrameCfoEvidence(
                scenario_id=scenario.scenario_id,
                frame_index=frame_index,
                local_frame_start_sample=round(frame_index * 10_000 / 3),
                absolute_frame_start_sample=20_000_000 + round(frame_index * 10_000 / 3),
                reference_time_s=time_s,
                occupied=True,
                status="complete",
                training_supported=True,
                training_rejection_reasons=(),
                coarse_seed_hz=round(truth.receiver_raw_cfo_hz / 750.0) * 750.0,
                alias_label_hz=truth.alias_label_hz,
                even_canonical_cfo_hz=truth.receiver_canonical_cfo_hz,
                odd_canonical_cfo_hz=truth.receiver_canonical_cfo_hz + odd_offset_hz,
                even_frequency_uncertainty_hz=1.0,
                odd_frequency_uncertainty_hz=1.0,
                even_exact_coherence=1.0,
                even_control_coherence=0.0,
                even_coherence_margin=1.0,
                even_exact_profile_max=0.0,
                even_control_profile_max=-10.0,
                odd_exact_profile_max=0.0,
                odd_control_profile_max=-10.0,
                even_profile_margin=10.0,
                odd_profile_margin=10.0,
                even_search_boundary=False,
                odd_search_boundary=False,
                receiver_truth_cfo_hz=truth.receiver_canonical_cfo_hz,
                physical_truth_cfo_hz=truth.physical_cfo_hz,
            )
        )
    return tuple(output)


def test_odd_qin_poison_cannot_change_fixed_histories_or_cubic() -> None:
    protocol = _protocol()
    scenario = replace(
        protocol.scenarios[0],
        rate_hz_s=3_500.0,
        acceleration_hz_s2=400.0,
        jerk_hz_s3=-120.0,
        alias_change_hz=750.0,
        cfo_step_hz=0.0,
        sample_clock_offset_ppm=0.0,
    )
    clean = _ideal_evidence(scenario, odd_offset_hz=0.0)
    poisoned = _ideal_evidence(scenario, odd_offset_hz=100_000.0)

    clean_rates = fixed_history_rate_estimates(clean, scenario, protocol)
    poisoned_rates = fixed_history_rate_estimates(poisoned, scenario, protocol)
    assert clean_rates == poisoned_rates
    assert fit_full_span_cubic(clean, scenario, protocol) == fit_full_span_cubic(
        poisoned, scenario, protocol
    )


def test_fixed_histories_retain_explicit_no_result_rows() -> None:
    protocol = _protocol()
    scenario = protocol.scenarios[0]

    rows = fixed_history_rate_estimates((), scenario, protocol)

    assert [row.estimator for row in rows] == [item.name for item in protocol.histories]
    assert all(row.status == "no_result" for row in rows)
    assert all(row.estimate_rate_hz_s is None for row in rows)


def test_all_histories_use_the_frozen_common_step_exclusion() -> None:
    protocol = _protocol()
    scenario = replace(
        protocol.scenarios[0],
        cfo_step_hz=300.0,
        alias_change_hz=0.0,
        sample_clock_offset_ppm=0.0,
    )

    rows = fixed_history_rate_estimates(
        _ideal_evidence(scenario, odd_offset_hz=0.0, frame_count=1_500),
        scenario,
        protocol,
    )

    after_short_history = [
        row
        for row in rows
        if row.status == "complete"
        and protocol.cfo_step_time_s + 0.125
        <= row.reference_time_s
        < protocol.cfo_step_time_s + protocol.step_transition_exclusion_s
    ]
    assert {row.estimator for row in after_short_history} == {
        "causal_20ms_linear",
        "fixed_125ms_linear",
        "fixed_500ms_linear",
    }
    assert {row.step_phase for row in after_short_history} == {"transition"}
    assert all(
        row.step_phase == "post_history"
        for row in rows
        if row.status == "complete"
        and row.reference_time_s >= protocol.cfo_step_time_s + protocol.step_transition_exclusion_s
    )


def test_full_span_cubic_recovers_receiver_coordinate_derivatives() -> None:
    protocol = _protocol()
    scenario = replace(
        protocol.scenarios[0],
        rate_hz_s=-3_500.0,
        acceleration_hz_s2=800.0,
        jerk_hz_s3=300.0,
        alias_change_hz=-750.0,
        cfo_step_hz=0.0,
        sample_clock_offset_ppm=25.0,
    )
    fit = fit_full_span_cubic(_ideal_evidence(scenario, odd_offset_hz=0.0), scenario, protocol)
    assert fit.status == "complete"
    assert np.isclose(fit.rate_hz_s, fit.receiver_rate_truth_hz_s, atol=1e-7)
    assert np.isclose(
        fit.acceleration_hz_s2,
        fit.receiver_acceleration_truth_hz_s2,
        atol=1e-7,
    )
    assert np.isclose(fit.jerk_hz_s3, fit.receiver_jerk_truth_hz_s3, atol=1e-6)
