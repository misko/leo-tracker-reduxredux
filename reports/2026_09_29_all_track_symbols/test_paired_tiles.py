import numpy as np
from paired_tiles import evaluate


def test_split_symbol_shift_recovery():
    rng = np.random.default_rng(31)
    a = rng.normal(size=(70, 8)) + 1j * rng.normal(size=(70, 8))
    b = np.zeros_like(a)
    b[1:, 1:] = a[:-1, :-1] * np.exp(0.8j)
    r = evaluate(a, b, 32)
    assert (r["time_shift"], r["carrier_shift"]) == (1, 1)
    assert np.isclose(r["shifted"], 1)
    assert len(r["real_signs"]) == 96


def test_random_receiver_does_not_validate_fitted_shift():
    rng = np.random.default_rng(71)
    scores = []
    for _ in range(100):
        a = rng.normal(size=(70, 8)) + 1j * rng.normal(size=(70, 8))
        b = rng.normal(size=(70, 8)) + 1j * rng.normal(size=(70, 8))
        scores.append(evaluate(a, b, 16)["shifted"])
    assert abs(np.mean(scores)) < 0.04
