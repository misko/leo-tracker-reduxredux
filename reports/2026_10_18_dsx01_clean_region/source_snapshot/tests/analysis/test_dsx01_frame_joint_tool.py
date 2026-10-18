"""Independent covariance checks for frame-linked bias priors."""

import sys
from math import lgamma
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from dsx01_frame_joint import linked_bias_covariance, pooled_fragment_groups  # noqa: E402
from dsx01_joint_marginal import integrated_gaussian  # noqa: E402


@pytest.mark.parametrize("sigma", [1000.0, 700.0, 300.0, 100.0])
def test_linking_preserves_marginals_and_only_declared_groups(sigma):
    c = linked_bias_covariance(6, [[0, 2, 3], [1, 4]], sigma)
    np.testing.assert_allclose(np.diag(c), 1.0, atol=1e-15)
    assert c[0, 2] == pytest.approx(1 - (sigma / 1000) ** 2)
    assert c[0, 1] == c[4, 5] == 0
    assert np.linalg.eigvalsh(c).min() > 0
    if sigma == 1000:
        np.testing.assert_array_equal(c, np.eye(6))


def test_linked_latent_density_matches_independent_dense_shared_bias_model():
    y = np.array([0.3, 1.2, -0.7, 1.8])
    u = np.array([[1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
    c = linked_bias_covariance(3, [[0, 1]], 300.0)
    result = integrated_gaussian(y, u @ np.linalg.cholesky(c), 2.0)
    covariance = 4 * np.eye(4) + u @ c @ u.T
    exact = y @ np.linalg.solve(covariance, y) + np.linalg.slogdet(covariance)[1] - 4 * np.log(4)
    assert result["residual"] @ result["residual"] == pytest.approx(exact, abs=1e-12)
    np.testing.assert_array_equal(
        pooled_fragment_groups(6, [[0, 2, 3], [1, 4]]), [0, 1, 0, 0, 1, 2]
    )


def test_duplicate_or_overlapping_groups_rejected():
    with pytest.raises(ValueError, match="disjoint"):
        linked_bias_covariance(3, [[0, 1], [1, 2]], 300.0)


def test_identity_proposal_preserves_original_rows_and_unrelated_candidates():
    from probe_dsx01_frame_identity import replace_labels

    original = dict(
        rows=[
            dict(component="a", candidate_index=2, candidate_norad=42, points=20),
            dict(component="b", candidate_index=3, candidate_norad=43, points=30),
        ],
        state=dict(beta=[0] * 8),
    )
    result = replace_labels(original, {"a"}, 3, 43)
    assert original["rows"][0]["candidate_index"] == 2
    assert result["rows"][0]["candidate_index"] == 3
    assert [r["points"] for r in result["rows"]] == [20, 30]
    assert result["rows"][1] == original["rows"][1]


def test_actual_residual_gate_does_not_refit_away_a_systematic_mean():
    from compare_dsx01_frame_joint import conditional_gate

    residual = np.random.default_rng(9).normal(0, 100, 80)
    centered = conditional_gate(residual, np.arange(80.0))
    shifted = conditional_gate(residual + 300, np.arange(80.0))
    assert centered["compatible"]
    assert shifted["rms_hz"] < 450
    assert not shifted["compatible"]
    assert shifted["diagnostics"]["mean_z"] > 10
    assert abs(shifted["mean_hz"] - centered["mean_hz"] - 300) < 1e-12


def test_pooled_noise_bound_has_correct_normalized_shared_student_density():
    from dsx01_hierarchical_bound import hierarchical_bound

    y = np.array([1.0, 2.0, 3.0, -0.5])
    for groups in [np.zeros(4, dtype=int), np.array([0, 0, 1, 1])]:
        result = hierarchical_bound(y, np.empty((4, 0)), np.ones(4), groups)
        logp = 0.0
        for k in np.unique(groups):
            local = y[groups == k]
            n = len(local)
            logp += lgamma((4 + n) / 2) - lgamma(2) - n / 2 * np.log(4 * np.pi)
            logp -= (4 + n) / 2 * np.log1p(local @ local / 4)
        assert result["negative_twice_elbo"] == pytest.approx(-2 * logp, abs=1e-12)
