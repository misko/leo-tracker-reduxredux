from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.fixed500_calibration import (
    FrozenCalibrationScenario,
    causal_quadratic_rates,
    grouped_conformal_multiplier,
    inject_resampled_exact_qin,
    load_frozen_scenarios,
    resampled_frame_starts,
    select_spaced_endpoints,
)
from leo.analysis.research.polynomial_injection import (
    FrameCfoEvidence,
    evaluate_exact_qin_frames,
    truth_at_receiver_time,
)
from leo.analysis.research.polynomial_injection_protocol import (
    InjectionScenario,
    load_polynomial_injection_protocol,
)

PROJECT_ROOT = Path(__file__).parents[2]
POLICY = PROJECT_ROOT / "config/analysis/doppler-experiment-dataset-policy-v1.json"
BASE_PROTOCOL = PROJECT_ROOT / "config/analysis/polynomial-phase-injection-protocol-v1.json"
CALIBRATION_PROTOCOL = PROJECT_ROOT / "config/analysis/fixed500-calibration-protocol-v1.json"


def _protocol():
    policy = load_doppler_dataset_policy(POLICY)
    return load_polynomial_injection_protocol(
        BASE_PROTOCOL,
        dataset_policy=policy,
        repository_root=PROJECT_ROOT,
    )


def _frozen_scenarios():
    protocol = _protocol()
    return protocol, load_frozen_scenarios(CALIBRATION_PROTOCOL, protocol=protocol)


def test_committed_design_expands_exact_split_on_only_three_authorized_backgrounds() -> None:
    protocol, frozen = _frozen_scenarios()

    assert len(frozen) == 36
    assert sum(item.split == "calibration" for item in frozen) == 18
    assert sum(item.split == "evaluation" for item in frozen) == 18
    assert {item.scenario.background_session_id for item in frozen} == {
        item.session_id for item in protocol.backgrounds
    }
    assert len({item.scenario.seed for item in frozen}) == 36
    primary = [
        item
        for item in frozen
        if item.split == "evaluation"
        and item.scenario.cfo_step_hz == 0.0
        and item.scenario.snr_db >= -12.0
        and item.scenario.frame_occupancy >= 0.70
    ]
    assert len(primary) == 12
    assert {
        background: sum(item.scenario.background_session_id == background for item in primary)
        for background in {item.scenario.background_session_id for item in primary}
    } == {item.session_id: 4 for item in protocol.backgrounds}


def test_protocol_mutation_that_expands_data_authority_fails_closed(tmp_path: Path) -> None:
    document = json.loads(CALIBRATION_PROTOCOL.read_text(encoding="utf-8"))
    document["input_authority"]["permitted_capture_ids"].append("cap-20260825T150802-473cb5bbcbd6")
    path = tmp_path / "mutated.json"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="backgrounds differ"):
        load_frozen_scenarios(path, protocol=_protocol())


def test_true_sample_clock_resamples_accumulated_lattice_and_waveform() -> None:
    protocol, frozen = _frozen_scenarios()
    scenario = next(
        item
        for item in frozen
        if item.scenario.sample_clock_offset_ppm == -50.0
        and item.scenario.background_session_id == protocol.backgrounds[0].session_id
    )
    compact_binding = replace(protocol.backgrounds[0], sample_count=10_000)
    compact_protocol = replace(
        protocol,
        backgrounds=(compact_binding,),
        frame_count=3,
        scenarios=(scenario.scenario,),
    )
    compact = FrozenCalibrationScenario(
        scenario.row_id,
        scenario.split,
        replace(
            scenario.scenario,
            background_session_id=compact_binding.session_id,
            snr_db=20.0,
            frame_occupancy=1.0,
        ),
    )
    background = np.asarray(1e-3 * (np.ones(10_000) + 1j * np.ones(10_000)), dtype=np.complex64)

    injected, occupied, starts, diagnostics = inject_resampled_exact_qin(
        background, compact, compact_protocol
    )
    evidence = evaluate_exact_qin_frames(
        injected,
        occupied,
        compact.scenario,
        compact_protocol,
        absolute_span_start_sample=20_000_000,
        frame_starts=starts,
        reference_offset_scale=diagnostics.clock_scale,
    )

    assert diagnostics.resampled_template_sample_count == 3_332
    assert diagnostics.clock_scale == pytest.approx(0.99995)
    assert diagnostics.complete_occupied_frame_count == 3
    assert tuple(item.local_frame_start_sample for item in evidence) == tuple(starts)
    assert all(item.training_supported for item in evidence[1:])

    nominal = resampled_frame_starts(
        frame_count=1_500, sample_rate_hz=2_500_000, sample_clock_offset_ppm=0.0
    )
    slow = resampled_frame_starts(
        frame_count=1_500, sample_rate_hz=2_500_000, sample_clock_offset_ppm=-50.0
    )
    fast = resampled_frame_starts(
        frame_count=1_500, sample_rate_hz=2_500_000, sample_clock_offset_ppm=50.0
    )
    assert slow[-1] - nominal[-1] == -250
    assert fast[-1] - nominal[-1] == 250


def _ideal_evidence(
    scenario: InjectionScenario, *, odd_offset_hz: float
) -> tuple[FrameCfoEvidence, ...]:
    protocol = _protocol()
    output = []
    for frame_index in range(750):
        reference_time_s = (frame_index + 0.5) / 750.0
        truth = truth_at_receiver_time(
            scenario,
            reference_time_s,
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
                reference_time_s=reference_time_s,
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


def test_quadratic_derivative_recovers_curvature_and_ignores_odd_qin() -> None:
    protocol = _protocol()
    scenario = replace(
        protocol.scenarios[0],
        rate_hz_s=3_500.0,
        acceleration_hz_s2=1_600.0,
        jerk_hz_s3=0.0,
        alias_change_hz=0.0,
        cfo_step_hz=0.0,
        sample_clock_offset_ppm=0.0,
    )
    clean = causal_quadratic_rates(_ideal_evidence(scenario, odd_offset_hz=0.0))
    poisoned = causal_quadratic_rates(_ideal_evidence(scenario, odd_offset_hz=100_000.0))

    assert clean == poisoned
    complete = [item for item in clean if item.status == "complete"]
    assert complete
    last = complete[-1]
    truth = truth_at_receiver_time(
        scenario,
        last.reference_time_s,
        carrier_origin_hz=protocol.carrier_origin_hz,
        reference_time_s=protocol.reference_time_s,
        alias_change_time_s=protocol.alias_change_time_s,
        cfo_step_time_s=protocol.cfo_step_time_s,
    )
    assert last.rate_hz_s == pytest.approx(truth.receiver_rate_hz_s, abs=1e-6)


def test_endpoint_and_grouped_quantile_rules_are_deterministic() -> None:
    selected = select_spaced_endpoints(
        np.asarray([10, 20, 30, 40]),
        np.asarray([0.49, 0.50, 1.01, 1.50]),
    )
    assert selected == (20, 30, 40)

    multiplier, order = grouped_conformal_multiplier([1.0, 4.0, 2.0, 3.0], confidence=0.95)
    assert order == 4
    assert multiplier == 4.0
