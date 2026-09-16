from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    coherent_pilot_frames,
    correlate_pilot_symbols,
    fit_linear_phasor,
    pilot_symbol_reference_offsets_s,
    restore_receiver_relative_phase,
)
from leo.analysis.starlink.templates import (
    CONTROL_SYMBOL_ROLL,
    FRAME_RATE_HZ,
    OFDM_SYMBOL_DURATION_S,
    qin_edge_pilot_frame,
)


def test_generated_dual_receiver_iq_recovers_phase_at_common_sample() -> None:
    sample_rate_hz = 2_500_000.0
    template = np.asarray(qin_edge_pilot_frame(sample_rate_hz, "lower"), np.complex128)
    control = np.asarray(
        qin_edge_pilot_frame(sample_rate_hz, "lower", symbol_roll=CONTROL_SYMBOL_ROLL),
        np.complex128,
    )
    symbols = np.arange(2, 66)
    starts = np.asarray(
        [5_000 + round(index * sample_rate_hz / FRAME_RATE_HZ) for index in range(9)]
    )
    references = (4_713, 4_719)
    actual_hz = (-80_321.25, -700_456.75)
    acquired_hz = (-80_000.0, -700_000.0)
    receiver_phase_rad = (-0.41, 0.83)
    common_frame_phase = np.asarray([0.2, -1.3, 2.1, 0.7, -2.4, 1.2, 2.8, -0.6, 1.7])
    iq = np.zeros((starts[-1] + len(template) + 1, 2), dtype=np.complex128)
    local = np.arange(len(template))
    for frame_index, start in enumerate(starts):
        absolute = start + local
        for receiver in (0, 1):
            phase = (
                common_frame_phase[frame_index]
                + receiver_phase_rad[receiver]
                + 2
                * np.pi
                * actual_hz[receiver]
                * (absolute - references[receiver])
                / sample_rate_hz
            )
            iq[absolute, receiver] += template * np.exp(1j * phase)

    offsets_s = pilot_symbol_reference_offsets_s(
        sample_rate_hz, OFDM_SYMBOL_DURATION_S, symbols, template
    )
    coherent = []
    for receiver in (0, 1):
        exact_corr = correlate_pilot_symbols(
            iq,
            starts,
            template,
            acquired_hz[receiver],
            references[receiver],
            receiver,
            symbols,
            sample_rate_hz,
            OFDM_SYMBOL_DURATION_S,
        )
        control_corr = correlate_pilot_symbols(
            iq,
            starts,
            control,
            acquired_hz[receiver],
            references[receiver],
            receiver,
            symbols,
            sample_rate_hz,
            OFDM_SYMBOL_DURATION_S,
        )
        frames, _, residual_hz, ratio = coherent_pilot_frames(
            exact_corr,
            control_corr,
            offsets_s,
            OFDM_SYMBOL_DURATION_S,
        )
        assert residual_hz == pytest.approx(actual_hz[receiver] - acquired_hz[receiver], abs=0.05)
        assert ratio > 10
        coherent.append(frames)

    product = coherent[1] * np.conj(coherent[0])
    center_sample = float(np.mean(starts))
    frame_times_s = starts / sample_rate_hz
    fitted_hz, product_phase_rad, concentration = fit_linear_phasor(
        product,
        frame_times_s,
        np.ones(len(starts)),
        center_sample / sample_rate_hz,
    )
    observed = restore_receiver_relative_phase(
        product_phase_rad,
        acquired_hz,
        center_sample,
        references,
        sample_rate_hz,
    )
    expected = (
        receiver_phase_rad[1]
        - receiver_phase_rad[0]
        + 2
        * np.pi
        * (
            actual_hz[1] * (center_sample - references[1])
            - actual_hz[0] * (center_sample - references[0])
        )
        / sample_rate_hz
    )

    assert fitted_hz == pytest.approx(
        (actual_hz[1] - acquired_hz[1]) - (actual_hz[0] - acquired_hz[0]),
        abs=0.01,
    )
    assert np.degrees(np.angle(np.exp(1j * (observed - expected)))) == pytest.approx(0.0, abs=0.03)
    assert concentration > 0.999999


def test_symbol_reference_uses_template_energy_centroid() -> None:
    template = np.zeros(30, dtype=np.complex128)
    template[12:15] = (1, 2, 3)

    offset = pilot_symbol_reference_offsets_s(10.0, 1.0, np.asarray([1]), template)

    expected = np.average(np.arange(10, 20), weights=abs(template[10:20]) ** 2) / 10
    assert offset[0] == pytest.approx(expected)


def test_phasor_fit_rejects_non_positive_weights() -> None:
    with pytest.raises(ValueError, match="weights and frequency interval"):
        fit_linear_phasor(
            np.ones(3, dtype=complex),
            np.arange(3, dtype=float),
            np.asarray([1.0, 0.0, 1.0]),
            1.0,
        )
