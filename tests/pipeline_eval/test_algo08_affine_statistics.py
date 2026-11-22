import numpy as np

from tools.pipeline_eval.variants.algo08_affine_statistics import AffineScore


def test_affine_normal_block_and_marginal_score_match_direct_rows():
    random = np.random.default_rng(10)
    terms = random.normal(size=(3, 126, 27))
    sigma = random.uniform(0.8, 2.1, size=126)
    weights = random.uniform(0.2, 1.1, size=126)
    prior = random.uniform(0.8, 2.1, size=26)
    patch = AffineScore(terms, sigma, weights, prior)
    for east, north in ((0., 0.), (4., -6.), (-0.1, 1.)):
        rows = (terms[0] + east * terms[1] + north * terms[2]) * (
            np.sqrt(weights) / sigma)[:, None]
        normal = rows.T @ rows
        np.testing.assert_allclose(patch.normal_at(east, north), normal, rtol=1e-12, atol=1e-12)
        features, raw = rows[:, :-1], rows[:, -1]
        gram = np.diag(prior) + features.T @ features
        coefficient = np.linalg.solve(gram, features.T @ raw)
        loss = np.sum((raw - features @ coefficient)**2) + np.sum(prior * coefficient**2)
        volume = np.linalg.slogdet(gram)[1] - np.log(prior).sum()
        np.testing.assert_allclose(patch.score(east, north), loss + volume, rtol=1e-12)
