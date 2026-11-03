"""Raw-state and total-time direction tests without corpus preparation."""

from types import SimpleNamespace

import numpy as np
import qualify
from numpy.testing import assert_allclose, assert_array_equal


def fixture(monkeypatch, fixed=False):
    basis = np.array([[1.0], [-1.0]]) / np.sqrt(2.0)
    v = np.zeros(9)
    v[7] = 20.0
    n = np.zeros(3)
    model = SimpleNamespace(
        basis=basis,
        clock_count=1,
        group_limits=np.array([2.0, 2.0]),
        group_scales=np.ones(2),
        labels=np.array([0]),
        scored_observations=SimpleNamespace(times_s=np.array([0.25])),
    )

    class Problem:
        def __init__(self, model, vector, rf_arm):
            self.lower = np.full(9, -100.0)
            self.upper = np.full(9, 100.0)
            self.scales = np.ones(9)
            self.start = vector.copy()
            self.start[7] -= 1e-9

        def constraints(self, vector):
            return 20.0 - abs(vector[7] + basis @ vector[8:])

    monkeypatch.setattr(qualify, "_Problem", Problem)
    return SimpleNamespace(
        model=model,
        vector=v,
        nuisance=n,
        fixed_c=fixed,
        bank=SimpleNamespace(numbers=np.array([11, 22]), nodes_s=np.arange(-30.0, 32.0)),
    )


def test_raw_boundary_not_constructor_nudged_and_independent_tau(monkeypatch):
    ctx = fixture(monkeypatch)
    plan = qualify.inventory(ctx)
    assert_array_equal(plan["vector"], ctx.vector)
    assert plan["fitter_constructor_margin_max_vector_difference"] > 0
    directions = [r for r in plan["coordinate_stencils"] if r["name"].startswith("total_tau")]
    for index, row in enumerate(directions):
        assert_allclose(
            row["dv"][7] + ctx.model.basis @ row["dv"][8:], np.eye(2)[index], atol=1e-15
        )
        assert row["stencil"]["kind"] == "one-sided-source-cell"
        assert row["stencil"]["h"] < 0
    assert plan["FDobjectives"] == 1 + 2 * plan["directions"]


def test_c0_skips_only_frozen_coefficient(monkeypatch):
    fitted = qualify.inventory(fixture(monkeypatch))
    zero = qualify.inventory(fixture(monkeypatch, fixed=True))
    def names(p):
        return {r["name"] for r in p["coordinate_stencils"]}

    assert names(fitted) - names(zero) == {"physical[6]"}
    assert zero["directions"] == fitted["directions"] - 1
