import numpy as np
from diagnose_stationarity import scaled_step


def test_equilibration_preserves_step_and_decrement_under_unit_changes():
    rng = np.random.default_rng(3)
    design = rng.normal(size=(15, 7))
    information = design.T@design + np.eye(7)
    rhs = rng.normal(size=7)
    step, decrement, _ = scaled_step(information, rhs)
    np.testing.assert_allclose(step, np.linalg.solve(information, rhs), rtol=1e-12)
    units = np.geomspace(1e-6, 1e6, 7)
    changed, changed_decrement, _ = scaled_step(
        information*units[:, None]*units[None, :], rhs*units)
    np.testing.assert_allclose(changed*units, step, rtol=1e-12)
    np.testing.assert_allclose(changed_decrement, decrement, rtol=1e-12)
