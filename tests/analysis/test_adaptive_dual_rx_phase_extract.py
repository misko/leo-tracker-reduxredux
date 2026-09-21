from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.starlink.adaptive_dual_rx_phase_extract import (
    ReceiverPhaseSeed,
    extract_dual_receiver_phase,
    shared_frame_starts,
)
from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

RATE = 2_500_000.0


def _synthetic_dual_iq() -> tuple[np.ndarray, int, tuple[ReceiverPhaseSeed, ReceiverPhaseSeed]]:
    template = np.asarray(qin_edge_pilot_frame(RATE, "lower"), np.complex128)
    epoch = 40_000
    starts = shared_frame_starts(100_000, RATE, epoch, frame_radius=9)
    references = (epoch - 316.63, epoch + 210.58)
    acquired = (-82_000.0, -701_000.0)
    actual = (-82_137.25, -701_296.75)
    receiver_phase = (-0.37, 0.91)
    common = np.random.default_rng(721).uniform(-np.pi, np.pi, len(starts))
    iq = np.zeros((100_000, 2), dtype=np.complex128)
    local = np.arange(len(template))
    for frame_index, start in enumerate(starts):
        absolute = start + local
        for receiver in (0, 1):
            phase = (
                common[frame_index]
                + receiver_phase[receiver]
                + 2 * np.pi * actual[receiver] * (absolute - references[receiver]) / RATE
            )
            iq[absolute, receiver] += template * np.exp(1j * phase)
    seeds = tuple(
        ReceiverPhaseSeed(acquired_cfo_hz=acquired[index], reference_sample=references[index])
        for index in (0, 1)
    )
    return iq, epoch, seeds  # type: ignore[return-value]


def test_extracts_phase_from_same_indices_and_restores_cfo_once() -> None:
    iq, epoch, seeds = _synthetic_dual_iq()

    result = extract_dual_receiver_phase(iq, RATE, "lower", epoch, seeds)

    assert result.receivers[0].frame_starts == result.receivers[1].frame_starts
    assert result.relative_frequency_hz == pytest.approx(-619159.5, abs=0.08)
    assert result.relative_frequency_standard_error_hz < 0.1
    expected = (
        0.91
        - (-0.37)
        + 2
        * np.pi
        * (
            -701296.75 * (result.center_sample - seeds[1].reference_sample)
            - -82137.25 * (result.center_sample - seeds[0].reference_sample)
        )
        / RATE
    )
    error_deg = np.degrees(np.angle(np.exp(1j * (result.wrapped_phase_rad - expected))))
    assert error_deg == pytest.approx(0.0, abs=0.04)
    assert result.resultant_length > 0.999999
    assert min(r.exact_to_control_power_ratio for r in result.receivers) > 10


def test_receiver_swap_negates_local_observable() -> None:
    iq, epoch, seeds = _synthetic_dual_iq()
    forward = extract_dual_receiver_phase(iq, RATE, "lower", epoch, seeds)
    reverse = extract_dual_receiver_phase(iq[:, ::-1], RATE, "lower", epoch, seeds[::-1])

    assert reverse.relative_frequency_hz == pytest.approx(-forward.relative_frequency_hz)
    assert np.angle(np.exp(1j * (reverse.wrapped_phase_rad + forward.wrapped_phase_rad))) == (
        pytest.approx(0.0, abs=1e-10)
    )


def test_frame_lattice_is_bounded_and_shared() -> None:
    starts = shared_frame_starts(20_000, RATE, 2_000, frame_radius=9)
    assert np.all(starts >= 0)
    assert np.all(starts + round(RATE / FRAME_RATE_HZ) <= 20_000)
    assert len(starts) < 19


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (np.zeros(20, dtype=np.complex64), "two complex receiver columns"),
        (np.zeros((20, 3), dtype=np.complex64), "two complex receiver columns"),
        (np.zeros((20, 2), dtype=np.float64), "two complex receiver columns"),
    ],
)
def test_rejects_non_dual_complex_iq(values: np.ndarray, message: str) -> None:
    seeds = (ReceiverPhaseSeed(0.0, 0.0), ReceiverPhaseSeed(0.0, 0.0))
    with pytest.raises(ValueError, match=message):
        extract_dual_receiver_phase(values, RATE, "lower", 0, seeds)
