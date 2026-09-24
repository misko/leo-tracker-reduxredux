"""Physical-coordinate invariants for chunked dual-RX phase extraction."""

import numpy as np

from leo.analysis.starlink.adaptive_dual_rx_phase import (
    restore_receiver_relative_phase,
    simultaneous_double_difference,
)


def _locally_derotated_product(
    physical_phase_at_center: float,
    frequencies_hz: tuple[float, float],
    center_sample: float,
    references: tuple[float, float],
    sample_rate_hz: float,
) -> float:
    """Simulate product phase after separate local receiver NCO references."""
    undone_by_restore = (
        2
        * np.pi
        * (
            frequencies_hz[1] * (center_sample - references[1])
            - frequencies_hz[0] * (center_sample - references[0])
        )
        / sample_rate_hz
    )
    return float(np.angle(np.exp(1j * (physical_phase_at_center - undone_by_restore))))


def test_chunk_origin_reset_restores_same_physical_receiver_phase():
    rate = 2_500_000.0
    frequencies = (372_727.25, -180_336.75)
    center = 67_510_000.5
    physical = 1.37
    # These emulate two separately started extractors on identical underlying IQ.
    first_refs = (67_500_000.0, 67_500_000.0)
    second_refs = (67_509_000.0, 67_511_500.0)
    first = restore_receiver_relative_phase(
        _locally_derotated_product(physical, frequencies, center, first_refs, rate),
        frequencies,
        center,
        first_refs,
        rate,
    )
    second = restore_receiver_relative_phase(
        _locally_derotated_product(physical, frequencies, center, second_refs, rate),
        frequencies,
        center,
        second_refs,
        rate,
    )
    assert abs(np.angle(np.exp(1j * (first - physical)))) < 1e-9
    assert abs(np.angle(np.exp(1j * (second - physical)))) < 1e-9
    assert abs(np.angle(np.exp(1j * (first - second)))) < 1e-9


def test_common_receiver_jump_cancels_but_source_dependent_jump_does_not():
    weights = np.ones(8)
    low = np.exp(1j * np.linspace(0.1, 0.3, 8))
    high = np.exp(1j * np.linspace(0.7, 0.9, 8))
    baseline, _ = simultaneous_double_difference(low, high, weights)
    # A receiver-differential jump applied equally to both sources cancels.
    common = 1.23
    same, _ = simultaneous_double_difference(
        low * np.exp(1j * common), high * np.exp(1j * common), weights
    )
    # A frequency/source-dependent response jump only on high cannot cancel.
    different, _ = simultaneous_double_difference(low, high * np.exp(1j * common), weights)
    assert abs(np.angle(np.exp(1j * (same - baseline)))) < 1e-12
    assert abs(np.angle(np.exp(1j * (different - baseline - common)))) < 1e-12


def test_double_difference_preserves_a_half_turn():
    phase, concentration = simultaneous_double_difference(
        np.ones(4, dtype=complex), -np.ones(4, dtype=complex), np.ones(4)
    )
    assert np.isclose(abs(phase), np.pi)
    assert np.isclose(concentration, 1.0)
