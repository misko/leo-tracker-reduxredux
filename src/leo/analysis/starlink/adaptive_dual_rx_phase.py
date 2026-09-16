"""Pure estimator primitives for adaptive dual-receiver pilot phase."""

from __future__ import annotations

import numpy as np

SYMBOL_ALIAS_HZ = 1 / 4.4e-6


def fit_linear_phasor(
    values: np.ndarray,
    times_s: np.ndarray,
    weights: np.ndarray,
    center_s: float,
    minimum_frequency_hz: float = -375.0,
    maximum_frequency_hz: float = 375.0,
) -> tuple[float, float, float]:
    """Fit a constant-frequency unit phasor at a declared reference time."""
    phasors = np.asarray(values, dtype=np.complex128)
    times = np.asarray(times_s, dtype=float)
    fit_weights = np.asarray(weights, dtype=float)
    if not (len(phasors) == len(times) == len(fit_weights) and len(phasors) > 0):
        raise ValueError("values, times, and weights must have one non-empty length")
    if not np.all(np.isfinite(times)) or not np.all(np.isfinite(fit_weights)):
        raise ValueError("times and weights must be finite")
    if np.any(fit_weights <= 0) or not minimum_frequency_hz < maximum_frequency_hz:
        raise ValueError("weights and frequency interval must be positive")
    unit = phasors / np.maximum(abs(phasors), 1e-30)

    def score(frequency_hz: float) -> float:
        rotated = unit * np.exp(-2j * np.pi * frequency_hz * (times - center_s))
        return float(abs(np.sum(fit_weights * rotated)))

    grid = np.linspace(
        minimum_frequency_hz,
        maximum_frequency_hz,
        max(3, int(np.ceil(maximum_frequency_hz - minimum_frequency_hz)) + 1),
    )
    scores = np.asarray([score(float(value)) for value in grid])
    peak = int(np.argmax(scores))
    left = float(grid[max(0, peak - 2)])
    right = float(grid[min(len(grid) - 1, peak + 2)])
    ratio = (np.sqrt(5.0) - 1.0) / 2.0
    x1 = right - ratio * (right - left)
    x2 = left + ratio * (right - left)
    y1, y2 = score(x1), score(x2)
    for _ in range(36):
        if y1 < y2:
            left, x1, y1 = x1, x2, y2
            x2 = left + ratio * (right - left)
            y2 = score(x2)
        else:
            right, x2, y2 = x2, x1, y1
            x1 = right - ratio * (right - left)
            y1 = score(x1)
    frequency_hz = (left + right) / 2
    corrected = unit * np.exp(-2j * np.pi * frequency_hz * (times - center_s))
    resultant = np.sum(fit_weights * corrected) / np.sum(fit_weights)
    return float(frequency_hz), float(np.angle(resultant)), float(abs(resultant))


def pilot_symbol_reference_offsets_s(
    sample_rate_hz: float,
    symbol_duration_s: float,
    symbol_indices: np.ndarray,
    template: np.ndarray,
) -> np.ndarray:
    """Return the effective time reference of each sampled symbol correlation.

    The correlation is referenced to the template-energy centroid of its
    included samples. Using these offsets avoids silently treating the first
    selected pilot symbol as the frame origin.
    """
    reference = np.asarray(template)
    if sample_rate_hz <= 0 or symbol_duration_s <= 0 or len(reference) <= 0:
        raise ValueError("sample rate, symbol duration, and template must be positive")
    symbols = np.asarray(symbol_indices, dtype=int)
    begins = np.rint(symbols * sample_rate_hz * symbol_duration_s).astype(int)
    ends = np.minimum(
        np.rint((symbols + 1) * sample_rate_hz * symbol_duration_s).astype(int),
        len(reference),
    )
    if np.any(ends <= begins):
        raise ValueError("every selected symbol must contain at least one sample")
    output = []
    for begin, end in zip(begins, ends, strict=True):
        indexes = np.arange(begin, end)
        energy = abs(reference[begin:end]) ** 2
        if float(np.sum(energy)) <= 0:
            raise ValueError("every selected symbol must have non-zero template energy")
        output.append(float(np.average(indexes, weights=energy) / sample_rate_hz))
    return np.asarray(output)


def correlate_pilot_symbols(
    iq: np.ndarray,
    frame_starts: np.ndarray,
    template: np.ndarray,
    frequency_hz: float,
    reference_sample: int,
    receiver: int,
    symbol_indices: np.ndarray,
    sample_rate_hz: float,
    symbol_duration_s: float,
) -> np.ndarray:
    """Correlate selected pilot symbols after phase-referenced CFO removal."""
    samples = np.asarray(iq)
    starts = np.asarray(frame_starts, dtype=int)
    symbols = np.asarray(symbol_indices, dtype=int)
    begins = np.rint(symbols * sample_rate_hz * symbol_duration_s).astype(int)
    ends = np.minimum(
        np.rint((symbols + 1) * sample_rate_hz * symbol_duration_s).astype(int),
        len(template),
    )
    width = int(np.max(ends - begins))
    offsets = begins[:, None] + np.arange(width)[None, :]
    mask = offsets < ends[:, None]
    safe_offsets = np.minimum(offsets, len(template) - 1)
    indexes = starts[:, None, None] + safe_offsets[None, :, :]
    received = samples[indexes, receiver]
    phase = 2 * np.pi * frequency_hz * (indexes - reference_sample) / sample_rate_hz
    corrected = received * np.exp(-1j * phase)
    reference = np.asarray(template)[safe_offsets] * mask
    return np.sum(corrected * np.conj(reference)[None, :, :], axis=2)


def coherent_pilot_frames(
    exact_correlations: np.ndarray,
    control_correlations: np.ndarray,
    symbol_reference_offsets_s: np.ndarray,
    symbol_duration_s: float,
    fft_size: int = 512,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Coherently sum pilot symbols with every frame referenced to its origin."""
    exact = np.asarray(exact_correlations, dtype=np.complex128)
    control = np.asarray(control_correlations, dtype=np.complex128)
    offsets = np.asarray(symbol_reference_offsets_s, dtype=float)
    if exact.shape != control.shape or exact.ndim != 2:
        raise ValueError("exact and control correlations must be matching matrices")
    if exact.shape[1] != len(offsets):
        raise ValueError("one symbol reference offset is required per correlation column")
    spectrum = np.fft.fft(exact, n=fft_size, axis=1)
    power = np.sum(abs(spectrum) ** 2, axis=0)
    coarse_hz = float(np.fft.fftfreq(fft_size, d=symbol_duration_s)[int(np.argmax(power))])

    def score(frequency_hz: float) -> float:
        rotation = np.exp(-2j * np.pi * frequency_hz * offsets)
        return float(np.sum(abs(np.sum(exact * rotation[None, :], axis=1)) ** 2))

    half_bin_hz = 1 / (2 * fft_size * symbol_duration_s)
    grid = coarse_hz + np.linspace(-half_bin_hz, half_bin_hz, 33)
    scores = np.asarray([score(float(value)) for value in grid])
    peak = int(np.argmax(scores))
    if 0 < peak < len(grid) - 1:
        x = grid[peak - 1 : peak + 2]
        y = scores[peak - 1 : peak + 2]
        curvature = y[0] - 2 * y[1] + y[2]
        adjustment = 0.0 if curvature == 0 else 0.5 * (y[0] - y[2]) / curvature
        adjustment = float(np.clip(adjustment, -1.0, 1.0))
        residual_hz = float(x[1] + adjustment * (x[1] - x[0]))
    else:
        residual_hz = float(grid[peak])
    rotation = np.exp(-2j * np.pi * residual_hz * offsets)
    exact_frames = np.sum(exact * rotation[None, :], axis=1)
    control_frames = np.sum(control * rotation[None, :], axis=1)
    ratio = float(
        np.sum(abs(exact_frames) ** 2) / max(float(np.sum(abs(control_frames) ** 2)), 1e-30)
    )
    return exact_frames, control_frames, residual_hz, ratio


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
        acquired_frequencies_hz[1] - acquired_frequencies_hz[0] + fitted_product_residual_hz
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
        anchor_frequency_hz = anchor[2]
        compatible = [
            edge
            for edge in edges
            if abs(circular_frequency_delta(anchor_frequency_hz, edge[2])) <= maximum_spread_hz
        ]
        left_nodes = sorted({edge[0] for edge in compatible})
        right_bits = {
            right: 1 << index
            for index, right in enumerate(sorted({edge[1] for edge in compatible}))
        }
        by_left = {left: [edge for edge in compatible if edge[0] == left] for left in left_nodes}

        def assignment_score(
            selected_edges: tuple[tuple[int, int, float, float], ...],
            anchor_hz: float = anchor_frequency_hz,
        ) -> tuple[int, float, float]:
            return (
                len(selected_edges),
                -sum(abs(circular_frequency_delta(anchor_hz, edge[2])) for edge in selected_edges),
                sum(edge[3] for edge in selected_edges),
            )

        assignments: dict[int, tuple[tuple[int, int, float, float], ...]] = {0: ()}
        for left in left_nodes:
            updated = dict(assignments)
            for used_right_mask, selected_edges in assignments.items():
                for edge in by_left[left]:
                    bit = right_bits[edge[1]]
                    if used_right_mask & bit:
                        continue
                    proposed = (*selected_edges, edge)
                    new_mask = used_right_mask | bit
                    incumbent = updated.get(new_mask)
                    if incumbent is None or assignment_score(proposed) > assignment_score(
                        incumbent
                    ):
                        updated[new_mask] = proposed
            assignments = updated
        selected = list(max(assignments.values(), key=assignment_score))
        spread = sum(
            abs(circular_frequency_delta(anchor_frequency_hz, edge[2])) for edge in selected
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


def circular_phase_standard_error_deg(resultant_length: float, independent_count: int) -> float:
    """Approximate standard error of a circular mean from concentration."""
    if independent_count < 1:
        raise ValueError("independent_count must be positive")
    bounded = min(max(float(resultant_length), 1e-12), 1.0)
    return float(np.degrees(np.sqrt(max(-2 * np.log(bounded), 0.0) / independent_count)))
