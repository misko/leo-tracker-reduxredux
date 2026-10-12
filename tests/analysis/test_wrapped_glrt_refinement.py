import numpy as np

from leo.analysis.sparse_glrt_likelihood import FrequencyEvidence
from leo.analysis.wrapped_glrt_likelihood import WrappedConfig, nuisance_design
from leo.analysis.wrapped_glrt_refinement import joint_value_gradient


def test_joint_gradient_matches_independent_differences_including_opportunity_and_weights():
    n = 80
    rng = np.random.default_rng(27)
    groups = np.arange(n) % 4
    times = np.linspace(0, 300, n)
    rf = 10.45e9 + 0.25e9 * ((groups % 2) * 4 + (np.arange(n) // 4) % 4 + 1)
    data = FrequencyEvidence(
        tuple(map(str, range(n))),
        rng.normal(0, 1000, (n, 2)),
        np.full((n, 2), 0.5),
        np.full(n, 0.95),
        groups,
        times,
    )
    design, _, span = nuisance_design(data, rf, coefficient=True)
    precision = np.r_[np.zeros(4), np.full(2, (10 * span) ** -2), 2000.0**-2]
    base = rng.normal(0, 1000, (n, 2))
    timing = rng.normal(0, 100, (n, 2))

    class Provider:
        def predict(self, t, indices=None):
            idx = np.arange(2) if indices is None else np.asarray(indices)
            t = np.asarray(t)
            pred = base[:, idx] + timing[:, idx] * t
            return (
                pred,
                np.broadcast_to(0.5 + 0.02 * t, pred.shape),
                timing[:, idx],
                np.full_like(pred, 0.02),
            )

    config = WrappedConfig(relative_phase_sigma_s=1.0, nuisance_solver="lbfgs")
    scales = np.r_[np.full(7, 250.0), 0.2, 0.3, 0.4]
    vector = rng.normal(0, 0.2, 12)
    args = (data, base, np.ones_like(base), design, precision, config, [0, 1], Provider(), scales)
    _, gradient = joint_value_gradient(vector, *args)
    numerical = np.zeros_like(vector)
    for i in range(len(vector)):
        shift = np.zeros_like(vector)
        shift[i] = 1e-5
        numerical[i] = (
            joint_value_gradient(vector + shift, *args)[0]
            - joint_value_gradient(vector - shift, *args)[0]
        ) / 2e-5
    np.testing.assert_allclose(gradient, numerical, rtol=1e-6, atol=1e-7)
