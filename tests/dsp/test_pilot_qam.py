from __future__ import annotations

import numpy as np
import pytest

from leo.analysis.qam import analyze_pilot_qam, combine_receiver_qam
from leo.analysis.starlink import NumericalStatus, qin_edge_pilot_frame
from leo.contracts.states import StarlinkEdge

RATE = 2_500_000.0
EPOCH = 37
ABSOLUTE_CFO_HZ = 201_170.0


def test_qam_has_no_implicit_edge() -> None:
    with pytest.raises(TypeError, match="edge"):
        analyze_pilot_qam(
            np.zeros(14_000, dtype=np.complex64),
            RATE,
            epoch_sample=0,
            absolute_cfo_hz=0.0,
        )


def _receiver(seed: int, noise: float, amplitude: float, phase: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = (
        rng.normal(0, noise / np.sqrt(2), 14_000) + 1j * rng.normal(0, noise / np.sqrt(2), 14_000)
    ).astype(np.complex128)
    template = qin_edge_pilot_frame(RATE, StarlinkEdge.LOWER)
    indexes = np.arange(template.size)
    for frame in range(4):
        start = EPOCH + round(frame * RATE / 750.0)
        values[start + indexes] += (
            amplitude
            * np.exp(1j * phase)
            * np.exp(2j * np.pi * ABSOLUTE_CFO_HZ * (start + indexes) / RATE)
            * template
        )
    return values


def test_per_receiver_and_inverse_noise_qam_metrics_match_oracle_goldens() -> None:
    left = analyze_pilot_qam(
        _receiver(20260819, 0.1, 2.0, 0.0),
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=ABSOLUTE_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )
    right = analyze_pilot_qam(
        _receiver(20260820, 0.25, 1.2, 0.6),
        RATE,
        epoch_sample=EPOCH,
        absolute_cfo_hz=ABSOLUTE_CFO_HZ,
        edge=StarlinkEdge.LOWER,
    )
    combined = combine_receiver_qam((left, right))

    assert left.metrics is not None and right.metrics is not None
    assert left.metrics.hard_symbol_accuracy == 1.0
    assert left.metrics.rms_evm == pytest.approx(0.155670166015625, abs=1e-12)
    assert right.metrics.hard_symbol_accuracy == pytest.approx(0.99875, abs=1 / 2400)
    assert combined.status is NumericalStatus.COMPLETE
    assert combined.metrics is not None
    assert combined.receiver_weights == pytest.approx(
        (0.5699193196725211, 0.4300806803274789), abs=1e-12
    )
    assert combined.metrics.hard_symbol_accuracy == pytest.approx(0.9995833333333334, abs=1 / 2400)
    assert combined.known_symbols_only is True
    assert combined.candidate_only is True


def test_qam_null_and_insufficient_results_are_not_exceptions_or_false_metrics() -> None:
    short = analyze_pilot_qam(
        np.ones(100, dtype=np.complex64),
        RATE,
        epoch_sample=0,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )
    null = analyze_pilot_qam(
        np.zeros(14_000, dtype=np.complex64),
        RATE,
        epoch_sample=0,
        absolute_cfo_hz=0.0,
        edge=StarlinkEdge.LOWER,
    )
    single = combine_receiver_qam((short,))

    assert short.status is NumericalStatus.INSUFFICIENT and short.metrics is None
    assert null.status is NumericalStatus.NO_RESULT and null.metrics is None
    assert single.status is NumericalStatus.INSUFFICIENT and single.metrics is None
