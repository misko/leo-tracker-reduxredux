from __future__ import annotations

import numpy as np
import pytest

import leo.analysis.qam.pilot as pilot_module
import leo.analysis.qam.pilot_even as pilot_even_module
from leo.analysis.qam import estimate_edge_pilot_frame_cfo_even_evidence
from leo.analysis.starlink import NumericalStatus, StarlinkEdge, qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S

RATE = 2_500_000.0
FRAME_START = 1_234_567
ACQUISITION_CFO_HZ = 200_000.0


def _raw_frame(*, residual_cfo_hz: float) -> np.ndarray:
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER), np.complex128)
    samples = np.zeros(frame_content + 2, dtype=np.complex128)
    indexes = np.arange(frame_content)
    samples[1 + indexes] = template[:frame_content] * np.exp(
        2j * np.pi * (ACQUISITION_CFO_HZ + residual_cfo_hz) * (FRAME_START + indexes) / RATE
    )
    return samples


def test_even_evidence_recovers_cfo_without_an_odd_response() -> None:
    injected_hz = 317.4

    result = estimate_edge_pilot_frame_cfo_even_evidence(
        _raw_frame(residual_cfo_hz=injected_hz),
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert result.training_supported
    assert result.training_rejection_reasons == ()
    assert result.residual_cfo_hz == pytest.approx(injected_hz, abs=0.5)
    assert result.exact_coherence is not None and result.exact_coherence > 0.97
    assert result.coherence_margin is not None and result.coherence_margin > 0.96
    assert result.odd_symbols_evaluated is False


def test_even_evidence_is_bitwise_invariant_to_odd_qin_samples() -> None:
    baseline_samples = _raw_frame(residual_cfo_hz=-281.25)
    perturbed_samples = baseline_samples.copy()
    generator = np.random.default_rng(20260825)
    for qin_position in range(1, 300, 2):
        symbol = qin_position + 2
        start = round(symbol * RATE * OFDM_SYMBOL_DURATION_S)
        stop = round((symbol + 1) * RATE * OFDM_SYMBOL_DURATION_S)
        count = stop - start
        perturbed_samples[1 + start : 1 + stop] = 1_000.0 * (
            generator.normal(size=count) + 1j * generator.normal(size=count)
        )

    baseline = estimate_edge_pilot_frame_cfo_even_evidence(
        baseline_samples,
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )
    perturbed = estimate_edge_pilot_frame_cfo_even_evidence(
        perturbed_samples,
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )

    assert perturbed == baseline


def test_even_evidence_calls_only_the_even_demodulation_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"even": 0}
    original_even_qin = pilot_even_module._demodulate_even_qin

    def watched_even_qin(
        samples: np.ndarray,
        sample_rate_hz: float,
        edge: StarlinkEdge,
        absolute_cfo_hz: float,
    ) -> np.ndarray:
        calls["even"] += 1
        return original_even_qin(samples, sample_rate_hz, edge, absolute_cfo_hz)

    def forbidden_full_frame(
        _demodulator: pilot_module._KnownPilotDemodulator,
        _frame_start: int,
    ) -> np.ndarray:
        raise AssertionError("the full all-Qin demodulation path was invoked")

    def forbidden_split(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("the even/odd split estimator was invoked")

    monkeypatch.setattr(
        pilot_even_module,
        "_demodulate_even_qin",
        watched_even_qin,
    )
    monkeypatch.setattr(
        pilot_module._KnownPilotDemodulator,
        "frame",
        forbidden_full_frame,
    )
    monkeypatch.setattr(
        pilot_module,
        "_estimate_edge_pilot_frame_cfo_split_from_cube",
        forbidden_split,
    )

    result = estimate_edge_pilot_frame_cfo_even_evidence(
        _raw_frame(residual_cfo_hz=137.5),
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )

    assert result.status is NumericalStatus.COMPLETE
    assert calls == {"even": 1}
    assert result.odd_symbols_evaluated is False


def test_even_evidence_returns_a_typed_zero_energy_rejection() -> None:
    frame_content = round(302 * RATE * OFDM_SYMBOL_DURATION_S)

    result = estimate_edge_pilot_frame_cfo_even_evidence(
        np.zeros(frame_content + 2, dtype=np.complex128),
        RATE,
        frame_start_sample=FRAME_START,
        acquisition_absolute_cfo_hz=ACQUISITION_CFO_HZ,
        edge=StarlinkEdge.UPPER,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert not result.training_supported
    assert result.training_rejection_reasons == ("zero_pilot_energy",)
    assert result.absolute_cfo_hz is None
    assert result.odd_symbols_evaluated is False
