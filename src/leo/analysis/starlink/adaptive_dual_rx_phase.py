"""Pure estimator primitives for adaptive dual-receiver pilot phase."""

from __future__ import annotations

import numpy as np

SYMBOL_ALIAS_HZ = 1 / 4.4e-6


def circular_frequency_delta(left_hz: float, right_hz: float) -> float:
    """Return the shortest symbol-alias-aware frequency displacement."""
    delta_hz = right_hz - left_hz
    return float(delta_hz - round(delta_hz / SYMBOL_ALIAS_HZ) * SYMBOL_ALIAS_HZ)


def restore_receiver_relative_phase(
    corrected_product_phase_rad: float,
    acquired_frequencies_hz: tuple[float, float],
    center_sample: float,
    reference_samples: tuple[int, int],
    sample_rate_hz: float,
) -> float:
    """Restore phase at a common sample without recounting GLRT residual CFO."""
    propagation_rad = (
        2
        * np.pi
        * (
            acquired_frequencies_hz[1] * (center_sample - reference_samples[1])
            - acquired_frequencies_hz[0] * (center_sample - reference_samples[0])
        )
        / sample_rate_hz
    )
    return float(np.angle(np.exp(1j * (corrected_product_phase_rad + propagation_rad))))


def receiver_relative_frequency_hz(
    acquired_frequencies_hz: tuple[float, float],
    fitted_product_residual_hz: float,
) -> float:
    """Combine the acquired frequencies with the receiver-product slope once."""
    return float(
        acquired_frequencies_hz[1]
        - acquired_frequencies_hz[0]
        + fitted_product_residual_hz
    )


def select_consistent_receiver_pairs(
    edges: list[tuple[int, int, float, float]],
    maximum_spread_hz: float = 10_000.0,
) -> list[tuple[int, int, float, float]]:
    """Select one-to-one pairs sharing one alias-aware RX frequency offset.

    Each edge is ``(rx0_index, rx1_index, rx1_minus_rx0_hz, quality)``.
    """
    best: list[tuple[int, int, float, float]] = []
    best_score: tuple[int, float, float] | None = None
    for anchor in edges:
        compatible = [
            edge
            for edge in edges
            if abs(circular_frequency_delta(anchor[2], edge[2]))
            <= maximum_spread_hz
        ]
        compatible.sort(
            key=lambda edge: (
                abs(circular_frequency_delta(anchor[2], edge[2])),
                -edge[3],
            )
        )
        selected: list[tuple[int, int, float, float]] = []
        used_left: set[int] = set()
        used_right: set[int] = set()
        for edge in compatible:
            if edge[0] in used_left or edge[1] in used_right:
                continue
            selected.append(edge)
            used_left.add(edge[0])
            used_right.add(edge[1])
        spread = sum(
            abs(circular_frequency_delta(anchor[2], edge[2])) for edge in selected
        )
        quality = sum(edge[3] for edge in selected)
        score = (len(selected), -spread, quality)
        if best_score is None or score > best_score:
            best = selected
            best_score = score
    return best


def simultaneous_double_difference(
    low_receiver_products: np.ndarray,
    high_receiver_products: np.ndarray,
    weights: np.ndarray,
) -> tuple[float, float]:
    """Estimate high-minus-low phase after cancelling the common frame phasor."""
    if not (
        len(low_receiver_products) == len(high_receiver_products) == len(weights)
        and len(weights) > 0
    ):
        raise ValueError("simultaneous products and weights must have one common length")
    products = high_receiver_products * np.conj(low_receiver_products)
    unit = products / np.maximum(abs(products), 1e-30)
    resultant = np.sum(weights * unit) / np.sum(weights)
    return float(np.angle(resultant)), float(abs(resultant))


def circular_phase_standard_error_deg(
    resultant_length: float, independent_count: int
) -> float:
    """Approximate standard error of a circular mean from concentration."""
    if independent_count < 1:
        raise ValueError("independent_count must be positive")
    bounded = min(max(float(resultant_length), 1e-12), 1.0)
    return float(
        np.degrees(np.sqrt(max(-2 * np.log(bounded), 0.0) / independent_count))
    )
