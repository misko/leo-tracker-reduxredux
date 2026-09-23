import numpy as np

from tools.research.evaluate_long_dwell_phase_change import (
    circular_abs_error,
    fit_circular_affine,
    sparse_indices,
    split_indices,
)


def test_sparse_split_is_reproducible_disjoint_and_complete():
    selected = sparse_indices(704)
    train, held = split_indices(len(selected))
    assert len(np.unique(selected)) == 16
    assert set(train).isdisjoint(held)
    assert set(train) | set(held) == set(range(16))


def test_circular_affine_recovers_wrapped_rate():
    time = np.linspace(0, 7, 12)
    phase = np.angle(np.exp(1j * (2.8 + 0.23 * time)))
    fit = fit_circular_affine(time, phase, 3.5)
    prediction = fit[0] + fit[1] * (time - 3.5)
    assert np.max(circular_abs_error(phase, prediction)) < 1e-9
    assert abs(fit[1] - 0.23) < 1e-9
