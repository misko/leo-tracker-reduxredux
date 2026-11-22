import importlib

import numpy as np
import pytest

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_anderson


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    folder = tmp_path_factory.mktemp("anderson")
    stock = native_bound.build(folder / "stock")
    alternate = folder / "anderson.so"
    algo08_anderson.build(alternate)
    return stock, alternate


def test_replays_exact_cold_finite_budget_on_exhaustion(compiled):
    stock, variant = compiled
    owner = native_bound.NativeBound(stock)
    rng = np.random.default_rng(5)
    groups = np.repeat(np.arange(4), [24, 29, 38, 26])
    n = len(groups)
    design = np.column_stack((rng.normal(0., 40., (n, 4)), np.eye(4)[groups] * 8))
    args = (rng.normal(0., 20., n), design, rng.uniform(2., 9., n), groups)
    try:
        expected = owner(*args, iterations=1)
        with algo08_anderson.accelerated(owner, variant) as counts:
            result = owner(*args, iterations=1)
        assert counts["native_calls"] == counts["cold_replays"] == counts["evaluations"] == 1
        assert counts["trials"] == 0
        assert result.keys() == expected.keys()
        for key, value in expected.items():
            assert np.asarray(value).tobytes() == np.asarray(result[key]).tobytes()
    finally:
        owner.clear()


def test_posterior_gate_catches_changes_when_objective_matches():
    trial = importlib.import_module("reports.ALGO08.single-core-2x.solver_anderson_trial")
    values = dict(negative_twice_elbo=9., noise_precision=np.array([0.025, .1]),
                  conditional_residual_hz=np.array([-15., 15.]), precision_iterations=256)
    changed = dict(values, noise_precision=np.array([0.0249, .1]), precision_iterations=130)
    errors, gates = trial.compare(values, changed)
    assert gates == dict(negative_twice_elbo=True, noise_precision=False,
                         conditional_residual_hz=True)
    assert errors["precision_iterations"] == 126
