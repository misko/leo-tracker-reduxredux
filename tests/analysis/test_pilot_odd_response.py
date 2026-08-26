from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import (
    estimate_edge_pilot_frame_complex_odd,
    estimate_edge_pilot_frame_complex_split,
)
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, StarlinkEdge

RATE_HZ = 2_500_000


def _guarded_frame(*, frame_start: int, cfo_hz: float) -> np.ndarray:
    frame_content = round(302 * RATE_HZ * OFDM_SYMBOL_DURATION_S)
    template = np.asarray(qin_edge_pilot_frame(RATE_HZ, StarlinkEdge.LOWER))[:frame_content]
    absolute = frame_start + np.arange(frame_content)
    guarded = np.zeros(frame_content + 2, dtype=np.complex128)
    guarded[1:-1] = template * np.exp(2j * np.pi * cfo_hz * absolute / RATE_HZ)
    return guarded


def test_odd_only_estimator_matches_split_odd_fold() -> None:
    frame_start = 1_000_000
    cfo_hz = 101_250.0
    guarded = _guarded_frame(frame_start=frame_start, cfo_hz=cfo_hz)

    odd = estimate_edge_pilot_frame_complex_odd(
        guarded,
        RATE_HZ,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=100_000.0,
        edge=StarlinkEdge.LOWER,
    )
    split = estimate_edge_pilot_frame_complex_split(
        guarded,
        RATE_HZ,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=100_000.0,
        edge=StarlinkEdge.LOWER,
    )

    assert odd.status is NumericalStatus.COMPLETE
    assert odd.odd is not None and split.odd is not None
    assert odd.odd.absolute_cfo_hz == pytest.approx(split.odd.absolute_cfo_hz, abs=1e-9)
    assert odd.odd.exact_coherence == pytest.approx(split.odd.exact_coherence, abs=1e-12)
    assert odd.odd.control_coherence == pytest.approx(split.odd.control_coherence, abs=1e-12)
    np.testing.assert_allclose(odd.odd.channel_vector, split.odd.channel_vector, atol=1e-12)


def test_target_even_qin_poison_cannot_change_odd_response() -> None:
    frame_start = 2_000_000
    guarded = _guarded_frame(frame_start=frame_start, cfo_hz=-75_750.0)
    baseline = estimate_edge_pilot_frame_complex_odd(
        guarded,
        RATE_HZ,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=-75_000.0,
        edge=StarlinkEdge.LOWER,
    )

    poisoned = guarded.copy()
    for qin_position in range(0, 300, 2):
        symbol = qin_position + 2
        start = round(symbol * RATE_HZ * OFDM_SYMBOL_DURATION_S)
        stop = round((symbol + 1) * RATE_HZ * OFDM_SYMBOL_DURATION_S)
        poisoned[1 + start : 1 + stop] = (9e8 + 7e8j) * (qin_position + 1)
    observed = estimate_edge_pilot_frame_complex_odd(
        poisoned,
        RATE_HZ,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=-75_000.0,
        edge=StarlinkEdge.LOWER,
    )

    assert baseline.odd is not None and observed.odd is not None
    assert observed.odd.absolute_cfo_hz == pytest.approx(baseline.odd.absolute_cfo_hz, abs=1e-12)
    assert observed.odd.frequency_uncertainty_hz == pytest.approx(
        baseline.odd.frequency_uncertainty_hz, abs=1e-12
    )
    assert observed.odd.exact_coherence == pytest.approx(baseline.odd.exact_coherence, abs=1e-12)
    assert observed.odd.control_coherence == pytest.approx(
        baseline.odd.control_coherence, abs=1e-12
    )
    np.testing.assert_array_equal(observed.odd.channel_vector, baseline.odd.channel_vector)

    nonfinite_poison = guarded.copy()
    for qin_position in range(0, 300, 2):
        symbol = qin_position + 2
        start = round(symbol * RATE_HZ * OFDM_SYMBOL_DURATION_S)
        stop = round((symbol + 1) * RATE_HZ * OFDM_SYMBOL_DURATION_S)
        nonfinite_poison[1 + start : 1 + stop] = (
            np.nan + 1j * np.inf if qin_position % 4 == 0 else np.inf + 1j * np.nan
        )
    nonfinite_observed = estimate_edge_pilot_frame_complex_odd(
        nonfinite_poison,
        RATE_HZ,
        frame_start_sample=frame_start,
        acquisition_absolute_cfo_hz=-75_000.0,
        edge=StarlinkEdge.LOWER,
    )
    assert nonfinite_observed.odd is not None
    assert nonfinite_observed.odd.absolute_cfo_hz == pytest.approx(
        baseline.odd.absolute_cfo_hz, abs=1e-12
    )


def test_odd_only_zero_energy_fails_closed_without_even_fields() -> None:
    frame_content = round(302 * RATE_HZ * OFDM_SYMBOL_DURATION_S)
    result = estimate_edge_pilot_frame_complex_odd(
        np.zeros(frame_content + 2, dtype=np.complex128),
        RATE_HZ,
        frame_start_sample=1,
        acquisition_absolute_cfo_hz=0.0,
        edge=StarlinkEdge.UPPER,
    )

    assert result.status is NumericalStatus.NO_RESULT
    assert result.odd is None
    assert "even" not in result.__dataclass_fields__
    assert "training_supported" not in result.__dataclass_fields__


def test_odd_only_rejects_non_one_dimensional_input() -> None:
    values = _guarded_frame(frame_start=1_000, cfo_hz=0.0)
    with pytest.raises(ValueError, match="one dimensional"):
        estimate_edge_pilot_frame_complex_odd(
            values.reshape(1, -1),
            RATE_HZ,
            frame_start_sample=1_000,
            acquisition_absolute_cfo_hz=0.0,
            edge=StarlinkEdge.LOWER,
        )
