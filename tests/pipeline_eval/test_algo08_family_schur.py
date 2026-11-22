import numpy as np
import pytest

from tools.pipeline_eval.variants import algo08_family_schur as variant


def fixture():
    rng = np.random.default_rng(76341)
    groups = np.repeat(np.arange(4), [7, 17, 12, 19])
    families = (0, 1, 0, 1)
    modes = ((3, 4), (5, 6, 7))
    design = np.zeros((len(groups), 12))
    design[:, :3] = rng.normal(size=(len(groups), 3))
    for i, f in enumerate(families):
        use = groups == i
        design[np.ix_(use, modes[f])] = rng.normal(size=(int(use.sum()), len(modes[f])))
        design[use, 8 + i] = 1.
    raw = rng.normal(size=len(groups))
    sigma = rng.uniform(0.5, 1.5, len(groups))
    return design, raw, sigma, groups, families, modes


def test_reduction_downdate_and_variational_moments_match_dense():
    u, y, sigma, g, families, modes = fixture()
    statistics = variant.TrackStatistics(u, y, sigma, g, families, 3, modes)
    priors = np.linspace(0.8, 2., u.shape[1])
    weights = np.linspace(0.2, 1.0, len(families))
    for weight, prior in ((weights, priors), (weights[::-1].copy(), priors**2)):
        reduced = statistics.reduce(weight, prior)
        for omit in (None, 0, 1):
            actual, diag, volume, cov = reduced.solve(omit=omit)
            use = np.ones(len(g), bool) if omit is None else np.asarray(families)[g] != omit
            a, b, groups = u[use] / sigma[use, None], y[use] / sigma[use], g[use]
            gram = np.diag(prior) + a.T @ (a * weight[groups, None])
            expected = np.linalg.solve(gram, a.T @ (b * weight[groups]))
            covariance = np.linalg.inv(gram)
            residual = b - a @ expected
            exp_energy = np.bincount(groups, weights=residual**2, minlength=len(families))
            exp_variance = np.bincount(groups, weights=np.sum((a @ covariance) * a, axis=1),
                                       minlength=len(families))
            energy, variance = variant.track_moments(statistics, actual, cov)
            np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0)
            np.testing.assert_allclose(diag, np.diag(covariance), atol=1e-12, rtol=0)
            np.testing.assert_allclose(energy, exp_energy, atol=1e-12, rtol=0)
            np.testing.assert_allclose(variance, exp_variance, atol=1e-12, rtol=0)
            assert volume == pytest.approx(np.linalg.slogdet(gram)[1] - np.log(prior).sum())


def test_misaligned_family_modes_cannot_silently_drop_a_column():
    design, raw, sigma, groups, families, modes = fixture()
    design[0, modes[1][0]] = 1.
    with pytest.raises(ValueError, match="Cross-family"):
        variant.TrackStatistics(design, raw, sigma, groups, families, 3, modes)
