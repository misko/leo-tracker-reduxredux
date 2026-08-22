from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.qam import PilotPhaseSlopeFrame
from leo.analysis.starlink import OFDM_SYMBOL_DURATION_S, StarlinkEdge, qin_edge_pilot_frame


def _tool():
    path = Path(__file__).parents[2] / "tools" / "report_edge_pilot_phase_slope_figures.py"
    spec = importlib.util.spec_from_file_location("edge_pilot_phase_slope_report_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _candidate(cfo_hz: float, margin: float, *, rank: int, epoch: int = 10) -> dict:
    return {
        "rank": rank,
        "local_epoch_sample": epoch,
        "acquired_cfo_hz": cfo_hz - 100.0,
        "scores": [
            {
                "method": "glrt64",
                "tracking_cfo_hz": cfo_hz,
                "margin": margin,
            }
        ],
    }


def test_selection_applies_margin_and_model_gates_before_stride() -> None:
    tool = _tool()
    trajectory = tool.FrozenTrajectory((1_000.0,), 0.0, "branch", "trajectory")
    scan = {
        "detections": [
            {
                "time_s": float(index),
                "sample_start": index * 100,
                "candidates": [
                    _candidate(1_050.0, 0.2, rank=0, epoch=index + 1),
                    _candidate(1_005.0, 0.1, rank=1, epoch=index + 2),
                ],
            }
            for index in range(6)
        ]
    }
    scan["detections"][1]["candidates"] = [_candidate(1_000.0, 0.01, rank=0)]
    scan["detections"][3]["candidates"] = [_candidate(4_000.0, 0.2, rank=0)]

    selected = tool._select_windows(
        scan,
        trajectory,
        start_s=0.0,
        end_s=5.0,
        minimum_margin=0.05,
        maximum_model_error_hz=100.0,
        accepted_stride=2,
    )

    assert [item.detection_time_s for item in selected] == [0.0, 4.0]
    assert all(item.candidate_rank == 1 for item in selected)
    assert selected[0].aligned_sample_start == 2
    assert selected[1].aligned_sample_start == 406


def test_phase_display_recovers_known_slope_without_connecting_frames() -> None:
    tool = _tool()
    expected = np.ones((300, 8), dtype=np.complex128)
    times_s = (np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S
    times_s -= np.mean(times_s)
    frequency_hz = 425.0
    phases = (-2.1, 1.7)
    channel = np.exp(1j * np.linspace(-1.2, 1.1, 8))
    pilots = np.asarray(
        [
            expected
            * channel[None, :]
            * np.exp(1j * (phase + 2 * np.pi * frequency_hz * times_s))[:, None]
            for phase in phases
        ]
    )
    frames = tuple(
        PilotPhaseSlopeFrame(
            frame_index=index,
            frame_start_sample=index * 3_333,
            reference_sample=1_661.0,
            residual_cfo_hz=frequency_hz,
            absolute_cfo_hz=100_000.0 + frequency_hz,
            frequency_uncertainty_hz=1.0,
            phase_at_reference_rad=phase,
            exact_coherence=1.0,
            control_coherence=0.0,
            coherence_margin=1.0,
            phase_residual_rms_rad=0.0,
        )
        for index, phase in enumerate(phases)
    )

    display, residual = tool._phase_arrays(pilots, expected, frames)

    np.testing.assert_allclose(display[:, 150], phases, atol=0.01)
    np.testing.assert_allclose(residual, 0.0, atol=1e-10)
    slopes = np.polyfit(times_s, display.T, 1)[0] / (2 * np.pi)
    np.testing.assert_allclose(slopes, frequency_hz, atol=1e-9)


def test_phase_update_runs_split_on_rejected_frames() -> None:
    tool = _tool()
    frames = tuple(
        SimpleNamespace(phase_update_applied=accepted)
        for accepted in (False, True, True, False, True, True, True, False)
    )

    runs = tool._phase_update_runs(frames)

    assert [len(run) for run in runs] == [2, 3]


def test_frequency_update_runs_split_on_rejected_frames() -> None:
    tool = _tool()
    frames = tuple(
        SimpleNamespace(frequency_update_applied=accepted)
        for accepted in (True, True, False, True, False)
    )

    runs = tool._frequency_update_runs(frames)

    assert [len(run) for run in runs] == [2, 1]


def test_strict_phase_update_runs_split_on_sampling_gaps() -> None:
    tool = _tool()
    frames = tuple(
        SimpleNamespace(phase_update_applied=True, reference_time_s=time_s)
        for time_s in (0.0, 1 / 750, 6 / 750, 7 / 750)
    )

    runs = tool._strict_phase_update_runs(frames)

    assert [len(run) for run in runs] == [2, 2]


def test_phase_segments_follow_reset_assigned_segment_ids() -> None:
    tool = _tool()
    frames = tuple(
        SimpleNamespace(phase_segment_id=segment_id) for segment_id in (0, 0, 1, 1, 1, 2)
    )

    segments = tool._phase_segments(frames)

    assert [len(segment) for segment in segments] == [2, 3, 1]


def test_coherent_stack_efficiency_recovers_common_phase_alignment() -> None:
    tool = _tool()
    channel = np.asarray((1 + 0.5j, -0.2 + 0.8j, 0.4 - 0.3j))
    phases = np.asarray((0.0, 0.9, -1.4, 2.2))
    rotated = np.exp(1j * phases)[:, None] * channel[None, :]
    corrected = rotated * np.exp(-1j * phases)[:, None]

    assert tool._coherent_stack_efficiency(rotated) < 0.5
    assert tool._coherent_stack_efficiency(corrected) == pytest.approx(1.0)


def test_wrapped_batch_polynomial_recovers_smooth_phase_across_cycles() -> None:
    tool = _tool()
    times = np.linspace(-0.04, 0.04, 61)
    truth = 0.3 + 95 * times - 800 * times**2 + 4_000 * times**3
    wrapped = np.angle(np.exp(1j * truth))

    _model, residual = tool._fit_wrapped_polynomial(
        times,
        wrapped,
        np.ones_like(times),
        degree=3,
    )

    np.testing.assert_allclose(residual, 0.0, atol=1e-9)


def test_phase_doubling_recovers_smooth_phase_with_binary_pi_states() -> None:
    tool = _tool()
    times = np.linspace(-0.04, 0.04, 60)
    truth = -0.2 + 80 * times - 600 * times**2
    states = ((np.arange(len(times)) * 7 + np.arange(len(times)) // 4) % 5 < 2).astype(int)
    observed = np.angle(np.exp(1j * (truth + np.pi * states)))

    _ordinary_model, ordinary_residual = tool._fit_wrapped_polynomial(
        times,
        observed,
        np.ones_like(times),
        degree=2,
    )
    _doubled_model, doubled_residual = tool._fit_wrapped_polynomial(
        times,
        np.angle(np.exp(2j * observed)),
        np.ones_like(times),
        degree=2,
    )

    assert np.sqrt(np.mean(ordinary_residual**2)) > 1.0
    np.testing.assert_allclose(0.5 * doubled_residual, 0.0, atol=1e-9)


def test_offline_channel_factorization_removes_fractional_timing_ramp() -> None:
    tool = _tool()
    sample_rate_hz = 2_500_000.0
    common = np.exp(1j * np.linspace(-0.8, 1.1, 8))
    common /= np.linalg.norm(common)
    delays = np.asarray((0.0, -0.35, 0.35, 0.05, -0.30, 0.30))
    phases = np.asarray((-2.0, -0.7, 0.4, 1.3, 2.1, 2.9))
    frequencies = tool.edge_frequencies_hz(tool.StarlinkEdge.UPPER)
    vectors = np.asarray(
        [
            common * np.exp(1j * phase) * np.exp(2j * np.pi * delay * frequencies / sample_rate_hz)
            for delay, phase in zip(delays, phases, strict=True)
        ]
    )

    estimated_delay, estimated_phase, similarity, corrected = (
        tool._separate_channel_delay_and_phase(
            vectors,
            np.ones(len(vectors)),
            sample_rate_hz=sample_rate_hz,
            edge=tool.StarlinkEdge.UPPER,
        )
    )

    np.testing.assert_allclose(
        estimated_delay - np.mean(estimated_delay),
        delays - np.mean(delays),
        atol=0.01,
    )
    relative_phase = np.angle(np.exp(1j * (estimated_phase - estimated_phase[0])))
    expected_phase = np.angle(np.exp(1j * (phases - phases[0])))
    np.testing.assert_allclose(relative_phase, expected_phase, atol=0.01)
    assert np.min(similarity) > 0.999
    assert tool._weighted_stack_efficiency(
        corrected * np.exp(-1j * estimated_phase)[:, None],
        np.ones(len(vectors)),
    ) == pytest.approx(1.0, abs=1e-5)


def test_complete_lattice_offline_audit_resolves_synthetic_pi_states() -> None:
    tool = _tool()
    sample_rate_hz = 2_500_000.0
    carrier_hz = 410_000.0
    reference_offset_s = float(
        np.mean((np.arange(300, dtype=float) + 2.5) * OFDM_SYMBOL_DURATION_S)
    )
    raw_sample_start = round((34.73 - reference_offset_s) * sample_rate_hz)
    starts = np.rint(np.arange(60) * sample_rate_hz / 750).astype(int)
    template = qin_edge_pilot_frame(sample_rate_hz, StarlinkEdge.UPPER)
    iq = np.zeros(starts[-1] + len(template) + 2, dtype=np.complex128)
    states = ((np.arange(len(starts)) * 7 + np.arange(len(starts)) // 4) % 5 < 2).astype(int)
    for index, start in enumerate(starts):
        iq[start : start + len(template)] += (-1) ** states[index] * template
    local_time_s = np.arange(len(iq)) / sample_rate_hz
    iq *= np.exp(2j * np.pi * carrier_hz * local_time_s)
    frames = tuple(
        SimpleNamespace(
            frame_start_sample=int(start),
            reference_time_s=(raw_sample_start + start + reference_offset_s * sample_rate_hz)
            / sample_rate_hz,
            phase_update_applied=True,
            phase_reset_detected=False,
        )
        for start in starts
    )
    trajectory = tool.FrozenTrajectory(
        (carrier_hz,),
        0.0,
        "synthetic-branch",
        "synthetic-trajectory",
    )

    result = tool._offline_phase_continuity_audit(
        iq,
        raw_sample_start=raw_sample_start,
        sample_rate_hz=sample_rate_hz,
        edge=StarlinkEdge.UPPER,
        trajectory=trajectory,
        dense_tracking=SimpleNamespace(frames=frames),
    )

    assert result.inferred_frame_count == 60
    assert result.quality_frame_count == 60
    assert result.frequency_fit_rms_hz < 1.0
    assert result.adjacent_phase_innovation_rms_rad > 1.0
    assert result.pi_centered_adjacent_phase_innovation_rms_rad < 5e-3
    assert result.cubic_batch_phase_residual_rms_rad > 1.0
    assert result.pi_ambiguity_batch_phase_residual_rms_rad < 1e-3
    assert result.pi_ambiguity_batch_stack_efficiency > 0.999
    assert result.even_to_odd_heldout_phase_residual_rms_rad < 1e-3
    assert result.odd_to_even_heldout_phase_residual_rms_rad < 1e-3
    assert result.heldout_pi_state_agreement == 1.0
    causal = result.causal_tracking
    assert causal.ordinary_phase_reset_count > 0
    assert causal.ordinary_phase_update_count < len(starts)
    assert causal.modulo_pi_phase_update_count == len(starts)
    assert causal.modulo_pi_phase_reset_count == 0
    assert causal.modulo_pi_phase_segment_count == 1
    assert causal.modulo_pi_ambiguity_transition_count == np.count_nonzero(np.diff(states))
    assert causal.modulo_pi_to_batch_state_agreement == 1.0
    assert causal.frame_timing_update_count == len(starts)
    assert causal.frame_phase_innovation_rms_s < 1e-9
