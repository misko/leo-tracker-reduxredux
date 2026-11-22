import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor
from tools.pipeline_eval.variants.experimental.receiver_differential_fold import (
    CODE,
    PERIOD,
    RATE,
    ROW_INDICES,
    coverage,
    pilot_filters,
    propose,
)


@pytest.mark.parametrize("carrier", [-721_000, 351_000])
def test_fold_recovers_timing_and_signed_carrier_with_arbitrary_frame_gains(carrier):
    rng = np.random.default_rng(807)
    code = rng.normal(size=CODE) + 1j * rng.normal(size=CODE)
    asset = np.zeros(4 * PERIOD + 81, dtype=np.float32)
    asset[:2 * PERIOD].view(np.complex64)[88:88 + 4 * CODE:4] = code
    asset[4 * PERIOD + 40] = 1
    signal = np.zeros(50_000, dtype=np.complex64)
    epoch = 817
    for frame, row in enumerate(ROW_INDICES):
        indices = row[epoch:epoch + CODE]
        phase = np.exp(1j * (rng.uniform(0, 2 * np.pi) + 2 * np.pi * carrier * indices / RATE))
        signal[indices] = (frame + 1) * code * phase
    assert coverage(Factor(0, 4 * epoch, 0, carrier, 1, 0),
                    *propose(signal, pilot_filters(asset), 0)) == (True, True)


def test_coverage_distinguishes_wrapped_phase_from_incorrect_signed_carrier():
    factor = Factor(1, 13_332, 0.2, 650_000, 1, 0)
    assert coverage(factor, [2], [(1, 2, -600_000)]) == (True, False)
    assert coverage(factor, [2], [(1, 2, 650_000)]) == (True, True)
