from types import SimpleNamespace

import numpy as np
import pytest
import run
from run import cases


def test_exact_new_membership_no_prior_seeds():
    plan = {
        "phases_bins": [-0.4, -0.2, 0, 0.2, 0.4],
        "amplitudes": [0.25, 1],
        "cutoffs_s": [0.00015, 0.001, 0.020],
        "seeds": list(range(127000, 127016)),
        "margin_gate": 0.025,
        "native_call_cap": 480,
    }
    inventory = cases(plan)
    assert len(inventory) == len(set(inventory)) == 480
    assert {c[3] for c in inventory}.isdisjoint(range(122000, 122016))
    plan["seeds"][0] = 122000
    with pytest.raises(AssertionError):
        cases(plan)


def test_measure_preserves_native_admission_and_bin(monkeypatch):
    z = np.zeros((1, 64), complex)
    monkeypatch.setattr(
        run,
        "_conditioned_correlation_workspace",
        lambda *a, **k: SimpleNamespace(select=lambda _: SimpleNamespace(values=z)),
    )
    generator = SimpleNamespace(signal=lambda *a, **k: (np.zeros(50, complex), 0.5))
    estimator = SimpleNamespace(glrt=lambda *a: (0.2, 0.1, 0.0))

    def refine(values, *, native_bin):
        assert native_bin == 0
        assert values is z
        return {"coarse_score": 0.2, "coarse_hz": 0.0, "logparabola_hz": 20.0, "newton_hz": 30.0}

    refinement = SimpleNamespace(DELTA_HZ=443.892, refine=refine)
    row = run.measure((0.2, 1, 0.001, 127000), generator, refinement, estimator)
    assert row["baseline"]["passed"]
    assert row["baseline"]["injected_hz"] == 0.2 * refinement.DELTA_HZ
    estimator.glrt = lambda *a: (0.1, 0.1, 0.0)
    with pytest.raises(ValueError, match="parity"):
        run.measure((0.2, 1, 0.001, 127000), generator, refinement, estimator)
