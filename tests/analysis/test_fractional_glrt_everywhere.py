from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import leo.analysis.starlink.pilot_methods as pilot_methods_module
from leo.analysis.standard.native_glrt_fractional import (
    build_standard_native_glrt_fractional_epoch_v2,
)
from leo.analysis.starlink.acquisition import (
    NumericalStatus,
    ReceiverFrequencyCalibration,
    SymbolwiseAcquisitionConfig,
    acquire_symbolwise,
)
from leo.analysis.starlink.fractional_epoch import (
    FractionalEpochStatus,
    build_fractional_epoch_refinement,
    circular_epoch_grid,
    fractional_take,
)
from leo.analysis.starlink.pilot_methods import (
    PilotMethod,
    PilotMethodCandidate,
    PilotMethodScore,
    PilotProbeDetection,
    conditioned_glrt64_score,
    refine_glrt64_epoch,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame
from leo.contracts.digests import canonical_digest
from leo.contracts.standard_native import StandardNativeSourceV2
from leo.contracts.standard_pipeline import StandardPathInputBindV5
from leo.contracts.states import StarlinkEdge

_RATES = (2_500_000, 3_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000, 25_000_000)


def _fractionally_delayed_pilot_probe(sample_rate_hz: int, delay_samples: float) -> np.ndarray:
    period_samples = round(sample_rate_hz / FRAME_RATE_HZ)
    period = np.zeros(period_samples, dtype=np.complex128)
    template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, "lower"), dtype=np.complex128)
    period[: min(len(period), len(template))] = template[:period_samples]
    bins = np.fft.fftfreq(period_samples)
    delayed = np.fft.ifft(np.fft.fft(period) * np.exp(-2j * np.pi * bins * delay_samples))
    return np.ascontiguousarray(np.tile(delayed, 15))


def test_circular_epoch_grid_wraps_both_sides_of_frame_seam() -> None:
    assert circular_epoch_grid(0, 3_000_000) == (3_998, 3_999, 0, 1, 2)
    assert circular_epoch_grid(3_999, 3_000_000) == (3_997, 3_998, 3_999, 0, 1)


def test_fractional_sampler_is_exact_on_integer_positions_and_bandlimited_between_them() -> None:
    indexes = np.arange(512, dtype=float)
    tone = np.exp(2j * np.pi * 0.071 * indexes)
    integer_positions = np.arange(20, 480, dtype=float)
    np.testing.assert_array_equal(fractional_take(tone, integer_positions), tone[20:480])

    positions = integer_positions + 0.37
    expected = np.exp(2j * np.pi * 0.071 * positions)
    np.testing.assert_allclose(fractional_take(tone, positions), expected, atol=1e-3, rtol=0.0)


@pytest.mark.parametrize("sample_rate_hz", _RATES)
def test_raw_iq_fractional_glrt_refinement_is_available_at_every_native_rate(
    sample_rate_hz: int,
) -> None:
    samples = _fractionally_delayed_pilot_probe(sample_rate_hz, 0.35)
    acquisition = acquire_symbolwise(
        samples,
        sample_rate_hz,
        ReceiverFrequencyCalibration("rx", 0.0, "0" * 64),
        edge="lower",
        config=SymbolwiseAcquisitionConfig(
            maximum_probe_samples=len(samples),
            retained_candidate_count=1,
        ),
    )
    assert acquisition.winner is not None
    winner = acquisition.winner
    integer_score = conditioned_glrt64_score(
        samples,
        sample_rate_hz,
        epoch_sample=winner.refined_epoch_sample,
        acquired_cfo_hz=winner.absolute_cfo_hz,
        edge="lower",
    )

    refinement = refine_glrt64_epoch(
        samples,
        sample_rate_hz,
        integer_epoch_sample=winner.refined_epoch_sample,
        acquired_cfo_hz=winner.absolute_cfo_hz,
        edge="lower",
        expected_integer_score=integer_score,
    )

    assert refinement.status is FractionalEpochStatus.COMPLETE
    assert refinement.fractional_epoch_offset_samples is not None
    assert refinement.fractional_exact_score is not None
    assert refinement.fractional_exact_score >= integer_score.exact_score - 1e-12
    assert refinement.exact_score_grid[2] == pytest.approx(integer_score.exact_score, abs=1e-12)


def test_raw_iq_fractional_glrt_refines_across_frame_seam() -> None:
    sample_rate_hz = 3_000_000
    samples = _fractionally_delayed_pilot_probe(sample_rate_hz, -0.35)
    integer_score = conditioned_glrt64_score(
        samples,
        sample_rate_hz,
        epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="lower",
    )

    refinement = refine_glrt64_epoch(
        samples,
        sample_rate_hz,
        integer_epoch_sample=0,
        acquired_cfo_hz=0.0,
        edge="lower",
        expected_integer_score=integer_score,
    )

    assert refinement.status is FractionalEpochStatus.COMPLETE
    assert refinement.wrapped_epoch_samples == (3_998, 3_999, 0, 1, 2)
    assert refinement.fractional_epoch_offset_samples == pytest.approx(-0.49, abs=0.08)
    assert refinement.fractional_frame_phase_sample == pytest.approx(3_999.51, abs=0.08)


def test_primary_qam_handoff_samples_iq_at_fractional_glrt_epoch(monkeypatch) -> None:
    observed_offsets: list[float] = []
    qam_result = SimpleNamespace(metrics=SimpleNamespace(hard_symbol_accuracy=0.91, rms_evm=0.12))

    def analyze(*_args, fractional_epoch_offset_samples, **_kwargs):
        observed_offsets.append(fractional_epoch_offset_samples)
        return qam_result

    monkeypatch.setattr("leo.analysis.qam.analyze_pilot_qam", analyze)
    candidate = PilotMethodCandidate(
        rank=0,
        local_epoch_sample=11,
        acquired_cfo_hz=25_000.0,
        scores=(),
        qam_accuracy=None,
        qam_evm=None,
        fractional_epoch_offset_samples=0.375,
        fractional_epoch_status=FractionalEpochStatus.COMPLETE.value,
    )
    observed_qam = []

    result = pilot_methods_module._with_fractional_primary_qam(
        np.ones(100, dtype=np.complex128),
        2_500_000,
        (candidate,),
        edge=StarlinkEdge.LOWER,
        primary_qam_observer=observed_qam.append,
    )

    assert observed_offsets == [0.375]
    assert observed_qam == [qam_result]
    assert result[0].qam_accuracy == pytest.approx(0.91)
    assert result[0].qam_evm == pytest.approx(0.12)


def test_v2_evidence_closes_one_complete_stateful_candidate() -> None:
    from tests.contracts.test_standard_path_input_bind_v4 import _values

    binding_values = _values(2_500_000)
    binding_values.update(
        schema_version=5,
        algorithm_version="standard-path-input-bind-v5",
    )
    binding = StandardPathInputBindV5.model_validate(
        {**binding_values, "binding_digest": canonical_digest(binding_values)}
    )
    source = StandardNativeSourceV2.from_path_binding(binding)
    refinement = replace(
        build_fractional_epoch_refinement(
            integer_epoch_sample=10,
            sample_rate_hz=2_500_000,
            exact_score_grid=(0.1, 0.5, 1.0, 0.5, 0.1),
            control_score_grid=(0.01, 0.02, 0.03, 0.02, 0.01),
        ),
        fractional_exact_score=1.0,
        fractional_control_score=0.03,
    )
    candidate = PilotMethodCandidate(
        rank=0,
        local_epoch_sample=10,
        acquired_cfo_hz=12_500.0,
        scores=(
            PilotMethodScore(
                method=PilotMethod.GLRT64,
                exact_score=1.0,
                control_score=0.03,
                margin=0.97,
                residual_cfo_hz=0.0,
                tracking_cfo_hz=12_500.0,
            ),
        ),
        qam_accuracy=None,
        qam_evm=None,
        fractional_epoch_offset_samples=refinement.fractional_epoch_offset_samples,
        fractional_epoch_status=refinement.status.value,
        fractional_epoch=refinement,
    )
    detection = PilotProbeDetection(
        status=NumericalStatus.COMPLETE,
        sample_start=0,
        time_s=0.0,
        local_epoch_sample=10,
        acquired_cfo_hz=12_500.0,
        scores=(),
        qam_accuracy=None,
        qam_evm=None,
        reason="fixture",
        candidates=(candidate,),
    )
    stateful_result = SimpleNamespace(
        path_input_binding_digest=source.path_input_binding_digest,
        validity_inventory_digest=source.validity_inventory_digest,
        sample_rate_hz=source.sample_rate_hz,
        segments=(
            SimpleNamespace(
                continuity_segment_index=1,
                device_sample_start=6,
                local_science=SimpleNamespace(detections=(detection,)),
            ),
        ),
    )
    stateful_path = SimpleNamespace(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
        stateful_path_digest=canonical_digest({"stateful": "path"}),
        science_configuration_digest=canonical_digest({"stateful": "configuration"}),
    )
    probe_schedule = SimpleNamespace(
        opportunities=(
            SimpleNamespace(
                probe=SimpleNamespace(sample_start=6),
                validity=SimpleNamespace(continuity_segment_index=1),
            ),
        )
    )
    full_capture = SimpleNamespace(
        source=source,
        starlink_edge=StarlinkEdge.LOWER,
        result_digest=canonical_digest({"full": "result"}),
        configuration_digest=canonical_digest({"full": "configuration"}),
    )

    result = build_standard_native_glrt_fractional_epoch_v2(
        stateful_result=stateful_result,
        stateful_path=stateful_path,
        stateful_path_product_digest=canonical_digest({"stateful": "product"}),
        probe_schedule=probe_schedule,
        full_capture_fractional=full_capture,
        full_capture_fractional_product_digest=canonical_digest({"full": "product"}),
    )

    assert result.candidate_refinement_count == result.complete_count == 1
    assert result.unbracketed_count == 0
    assert result.refinements[0].first_supported_global_epoch_device_sample == 16.0
