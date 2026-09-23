import numpy as np

from leo.analysis.qam.pilot import estimate_edge_pilot_frame_complex_split
from leo.analysis.starlink import qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge
from tools.research.longarc_phase_transport import (
    carrier_cycles_from_frequency,
    saved_reference_counter,
    transport_vectors,
    vector_increment_rad,
    wrap_pi,
)

RATE = 2_500_000.0
CONTENT = round(302 * RATE * OFDM_SYMBOL_DURATION_S)


def _physical_slice(global_start: int, carrier_hz: float, phase_rad: float) -> np.ndarray:
    template = np.asarray(qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER), complex)
    result = np.zeros(CONTENT + 2, complex)
    samples = global_start + np.arange(CONTENT)
    result[1:-1] = template[:CONTENT] * np.exp(
        2j * np.pi * carrier_hz * samples / RATE + 1j * phase_rad
    )
    return result


def test_shifted_slice_origins_need_no_extra_start_rotation():
    """Raw IQ phase carries the physical origin through local-NCO cancellation."""
    carrier = 123_456.7
    origin = 91_000_000
    local_starts = np.array([12_000, 32_000])
    vectors, times = [], []
    for local_start in local_starts:
        # The estimator receives a local frame coordinate, as the long-arc
        # replay does, while the synthesized IQ has a physical capture origin.
        item = estimate_edge_pilot_frame_complex_split(
            _physical_slice(origin + int(local_start), carrier, 0.31),
            RATE,
            frame_start_sample=int(local_start),
            acquisition_absolute_cfo_hz=120_000.0,
            edge=StarlinkEdge.LOWER,
        )
        assert item.even is not None
        vectors.append(item.even.channel_vector)
        times.append((origin + item.reference_sample) / RATE)

    observed = vector_increment_rad(vectors[0], vectors[1])
    expected = wrap_pi(2 * np.pi * carrier * (times[1] - times[0]))
    np.testing.assert_allclose(observed, expected, atol=0.03)

    transported = transport_vectors(np.asarray(vectors), np.asarray(times), np.full(2, carrier))
    assert abs(vector_increment_rad(transported[0], transported[1])) < 0.03


def test_saved_reference_is_integer_grid_and_fraction_is_not_silently_added():
    observation = {
        "valid_start_counter": 1_000_000,
        "fractional_epoch_offset_samples": 0.37,
    }
    frame = {"frame": {"reference_sample": 12_345.5}}
    assert saved_reference_counter(frame, observation, 900_000) == 112_345.5


def test_trapezoidal_cycles_match_linear_frequency_integral():
    times = np.array([0.0, 0.001, 0.003])
    frequency = 100.0 + 20.0 * times
    np.testing.assert_allclose(
        carrier_cycles_from_frequency(times, frequency),
        100.0 * times + 10.0 * times**2,
        atol=1e-14,
    )
