from __future__ import annotations

import math

import numpy as np
import pytest

from leo.analysis.starlink.dual_rx_multisource_phase import (
    DifferentialDelayCalibration,
    IndependentPairPhase,
    PhaseIdentifiability,
    SharedSourceTransfer,
    SharedTransferBlock,
    estimate_multisource_phase,
    independent_three_source_closure,
)


def _wrap(value: float) -> float:
    return float(np.angle(np.exp(1j * value)))


def _narrowband_source(
    count: int, rate: float, frequency_hz: float, rng: np.random.Generator
) -> np.ndarray:
    frequencies = np.fft.fftfreq(count, d=1 / rate)
    distance = abs((frequencies - frequency_hz + rate / 2) % rate - rate / 2)
    spectrum = np.zeros(count, dtype=complex)
    support = distance <= 2_500.0
    spectrum[support] = rng.normal(size=sum(support)) + 1j * rng.normal(size=sum(support))
    waveform = np.fft.ifft(spectrum)
    return waveform / np.sqrt(np.mean(abs(waveform) ** 2))


def _fractional_delay(values: np.ndarray, rate: float, delay_s: float) -> np.ndarray:
    frequencies = np.fft.fftfreq(len(values), d=1 / rate)
    return np.fft.ifft(np.fft.fft(values) * np.exp(-2j * np.pi * frequencies * delay_s))


def _matched_amplitude(reference: np.ndarray, received: np.ndarray) -> tuple[complex, float]:
    amplitude = np.vdot(reference, received) / np.vdot(reference, reference)
    coherence = abs(np.vdot(reference, received)) / math.sqrt(
        float(np.vdot(reference, reference).real * np.vdot(received, received).real)
    )
    return complex(amplitude), float(coherence)


def test_injected_shared_waveforms_recover_conditional_phase_and_reject_aliases() -> None:
    rate = 1_000_000.0
    count = 16_384
    time = np.arange(count) / rate
    frequencies = {"a": -160_000.0, "b": 20_000.0, "c": 210_000.0}
    receiver_cfo_hz = 3_051.7578125
    differential_delay_s = 0.37 / rate
    rng = np.random.default_rng(20260921)
    sources = {
        source_id: _narrowband_source(count, rate, frequency, rng)
        for source_id, frequency in frequencies.items()
    }
    geometry = {
        0: {"a": 0.20, "b": -0.70, "c": 1.10},
        1: {"a": 0.21, "b": -0.685},  # C is outside RX1 visibility.
        2: {"a": 0.22, "b": -0.67, "c": 1.06},
    }
    receiver_phase = (0.30, 0.73, -0.41)
    receiver_phase_rate_rad_s = (8.0, -6.0, 4.0)
    amplitudes = {
        "a": (1.0, 0.55),
        "b": (0.65, 1.25),
        "c": (1.35, 0.42),
    }
    blocks = []
    correct_coherences = []
    wrong_alias_coherences = []
    for block_index, phases in geometry.items():
        rx0 = np.zeros(count, dtype=complex)
        rx1 = np.zeros(count, dtype=complex)
        for source_id, phase in phases.items():
            source = sources[source_id]
            amp0, amp1 = amplitudes[source_id]
            rx0 += amp0 * source
            delayed = _fractional_delay(source, rate, differential_delay_s)
            rx1 += amp1 * delayed * np.exp(1j * phase)
        receiver_phase_path = receiver_phase[block_index] + receiver_phase_rate_rad_s[
            block_index
        ] * (time - np.mean(time))
        rx1 *= np.exp(1j * (receiver_phase_path + 2 * np.pi * receiver_cfo_hz * time))
        rx0 += 0.015 * (rng.normal(size=count) + 1j * rng.normal(size=count))
        rx1 += 0.015 * (rng.normal(size=count) + 1j * rng.normal(size=count))
        transfers = []
        for source_id in phases:
            source = sources[source_id]
            rx0_amplitude, coherence0 = _matched_amplitude(source, rx0)
            receiver_reference = source * np.exp(2j * np.pi * receiver_cfo_hz * time)
            rx1_amplitude, coherence1 = _matched_amplitude(receiver_reference, rx1)
            transfers.append(
                SharedSourceTransfer(
                    source_id=source_id,
                    baseband_frequency_hz=frequencies[source_id],
                    rx1_times_conjugate_rx0=rx1_amplitude * np.conj(rx0_amplitude),
                    weight=min(coherence0, coherence1) ** 2,
                )
            )
            correct_coherences.append(coherence1)
            for alias_hz in (750.0, 227_272.72727272726):
                alias_reference = source * np.exp(2j * np.pi * (receiver_cfo_hz + alias_hz) * time)
                _, wrong = _matched_amplitude(alias_reference, rx1)
                wrong_alias_coherences.append(wrong)
        blocks.append(
            SharedTransferBlock(
                block_id=f"block-{block_index}",
                common_time_s=0.020 * block_index,
                sources=tuple(transfers),
            )
        )

    unresolved = estimate_multisource_phase(tuple(blocks))
    assert unresolved.identifiability is PhaseIdentifiability.COMBINED_GEOMETRY_AND_INSTRUMENT
    assert unresolved.affine_frequency_nullspace is not None
    assert len(unresolved.pair_differences) == 7

    calibrated = estimate_multisource_phase(
        tuple(blocks),
        delay_calibration=DifferentialDelayCalibration(
            delay_s=differential_delay_s,
            standard_error_s=5e-9,
            authority="independent injected cable-delay calibration",
        ),
    )
    expected_identifiability = PhaseIdentifiability.DELAY_CORRECTED_GEOMETRY_AND_INSTRUMENT
    assert calibrated.identifiability is expected_identifiability
    for estimate in calibrated.pair_differences:
        block_index = int(estimate.block_id.removeprefix("block-"))
        expected = _wrap(
            geometry[block_index][estimate.source_b] - geometry[block_index][estimate.source_a]
        )
        assert estimate.delay_corrected_combined_phase_rad == pytest.approx(expected, abs=0.02)
        assert estimate.delay_correction_standard_error_rad == pytest.approx(
            2 * np.pi * abs(estimate.frequency_difference_hz) * 5e-9
        )
    assert min(correct_coherences) > 0.2
    assert max(wrong_alias_coherences) < min(correct_coherences) / 5


def test_independent_three_source_closure_exposes_one_bad_pair() -> None:
    ab = IndependentPairPhase("block", "a", "b", 0.4)
    bc = IndependentPairPhase("block", "b", "c", -0.7)
    ac = IndependentPairPhase("block", "a", "c", -0.29)

    assert independent_three_source_closure(ab, bc, ac) == pytest.approx(-0.01)
    assert abs(
        independent_three_source_closure(
            ab,
            bc,
            IndependentPairPhase("block", "a", "c", 0.51),
        )
    ) == pytest.approx(0.81)


def test_delay_nullspace_changes_conditional_phase_without_changing_observable() -> None:
    frequencies = {"a": -100_000.0, "b": 200_000.0, "c": 350_000.0}
    geometry = {"a": 0.2, "b": -0.5, "c": 1.1}
    delay_s = 40e-9
    gauge_shift_s = 100e-9
    receiver_phase = 0.3

    def phasor(source_id: str, source_phase: float, delay: float) -> complex:
        return np.exp(
            1j * (receiver_phase + source_phase - 2 * np.pi * frequencies[source_id] * delay)
        )

    original_phasors = {
        source_id: phasor(source_id, geometry[source_id], delay_s) for source_id in frequencies
    }
    gauge_equivalent_phasors = {
        source_id: phasor(
            source_id,
            geometry[source_id] + 2 * np.pi * frequencies[source_id] * gauge_shift_s,
            delay_s + gauge_shift_s,
        )
        for source_id in frequencies
    }
    assert gauge_equivalent_phasors == pytest.approx(original_phasors, abs=1e-12)
    block = SharedTransferBlock(
        block_id="block",
        common_time_s=1.0,
        sources=tuple(
            SharedSourceTransfer(source_id, frequencies[source_id], phasor_value, 3.0)
            for source_id, phasor_value in original_phasors.items()
        ),
    )
    first = estimate_multisource_phase(
        (block,),
        delay_calibration=DifferentialDelayCalibration(0.0, 0.0, "first"),
    ).pair_differences[0]
    second = estimate_multisource_phase(
        (block,),
        delay_calibration=DifferentialDelayCalibration(100e-9, 0.0, "second"),
    ).pair_differences[0]

    assert first.combined_phase_rad == second.combined_phase_rad
    assert second.delay_corrected_combined_phase_rad == pytest.approx(
        _wrap(first.delay_corrected_combined_phase_rad + 2 * np.pi * 300_000 * 100e-9)
    )
