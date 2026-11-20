"""Validate fixed aliases, Gaussian scores, and near-tie order against the dense oracle."""

import numpy as np
import pytest
from scipy.linalg import solve_triangular

from tools.pipeline_eval.qualification import cavity_covariance as overlay
from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.variants import cavity_covariance as low


def dense(y, r, f, d, sd, covariance, groups):
    root = np.linalg.cholesky(covariance)
    raw = y[None, :] - r[None, :] - f
    aliases = np.column_stack(
        [
            np.rint(-raw[:, groups == k].mean(axis=1) / low.PERIOD).astype(int)
            for k in range(1 + int(groups.max()))
        ]
    )
    raw = raw + aliases[:, groups] * low.PERIOD
    b = solve_triangular(root, raw.T, lower=True)
    a = solve_triangular(root, (d * sd[:, None]).T, lower=True)
    norm, projection = np.sum(a * a, axis=0), np.sum(a * b, axis=0)
    score = np.sum(b * b, axis=0) - projection**2 / (1 + norm) + np.log1p(norm)
    score += 2 * np.log(np.diag(root)).sum() + len(y) * np.log(2 * np.pi)
    return dict(score=score, aliases=aliases, phase_z=projection / (1 + norm))


def inputs(seed, count=117, n=75, width=9):
    rng = np.random.default_rng(seed)
    groups = np.arange(n) % 4
    noise = rng.uniform(5, 280, n)
    radio = rng.normal(size=(n, width))
    prior = rng.normal(size=(width, width))
    cov = low.BaseCovariance(noise, radio, prior @ prior.T + np.eye(width), groups)
    y, r = (rng.normal(scale=9e4, size=n) for _ in range(2))
    frequencies, rates = (rng.normal(scale=scale, size=(count, n)) for scale in (7e4, 2500))
    phases = rng.uniform(0.1, 8, count)
    return y, r, frequencies, rates, phases, cov, groups


@pytest.mark.parametrize("seed", [1, 210, 983])
def test_mode_space_reproduces_every_candidate_rank_and_alias(seed):
    y, r, f, d, sd, cov, groups = inputs(seed)
    expected = dense(y, r, f, d, sd, cov.dense(), groups)
    telemetry = []

    def unexpected(*args):
        pytest.fail("unambiguous ranks must stay in mode space")

    actual = low.coarse_phase_scores(
        y, r, f, d, sd, cov, groups, stock=unexpected, telemetry=telemetry
    )
    assert not telemetry[0]["dense_fallback"]
    assert np.array_equal(actual["aliases"], expected["aliases"])
    assert np.array_equal(np.argsort(actual["score"]), np.argsort(expected["score"]))
    assert np.allclose(actual["score"], expected["score"], rtol=2e-11)
    assert np.allclose(actual["phase_z"], expected["phase_z"], rtol=2e-11, atol=1e-11)


def test_close_ranks_resolve_with_the_unmodified_dense_order():
    y, r, f, d, sd, cov, groups = inputs(481, count=19)
    f[-1], d[-1], sd[-1] = f[1], d[1], sd[1]
    telemetry = []
    actual = low.coarse_phase_scores(y, r, f, d, sd, cov, groups, stock=dense, telemetry=telemetry)
    expected = dense(y, r, f, d, sd, cov.dense(), groups)
    assert telemetry[0]["dense_fallback"]
    assert all(np.array_equal(actual[k], expected[k]) for k in expected)


def test_half_integer_alias_uses_original_raw_arithmetic():
    n = 8
    group = np.repeat([0, 1], n // 2)
    y = np.zeros(n)
    f = np.array([0.5, 1.5, -2.5, -3.5])[:, None] * low.PERIOD * np.ones((4, n))
    d = np.repeat([1, 2, 3, 4], n).reshape(4, n)
    cov = low.BaseCovariance(np.full(n, 40), np.ones((n, 1)), np.eye(1), group)
    actual = low.coarse_phase_scores(y, y, f, d, np.ones(4), cov, group, stock=dense, telemetry=[])
    assert np.array_equal(actual["aliases"], np.repeat([[0], [2], [-2], [-4]], 2, axis=1))


def original_family(noise, radio, cov, groups):
    radio_width = radio.shape[1]
    covariance = (
        np.diag(noise**2)
        + radio @ cov[:radio_width, :radio_width] @ radio.T
        + 300.0**2 * (groups[:, None] == groups[None, :])
    )
    return dict(base_covariance=covariance, keep=groups.copy())


def test_overlay_replaces_only_the_reviewed_covariance_expression():
    *_, covariance, groups = inputs(42)
    arguments = (covariance.noise, covariance.radio, covariance.radio_covariance, groups)
    altered = overlay._overlay(original_family)(*arguments)
    dense_original = original_family(*arguments)
    assert isinstance(altered["base_covariance"], low.BaseCovariance)
    assert np.array_equal(altered["base_covariance"].dense(), dense_original["base_covariance"])
    assert np.array_equal(altered["keep"], dense_original["keep"])


def test_frozen_overlay_rejects_altered_source_bytes(tmp_path, monkeypatch):
    directory = tmp_path / "leo" / "analysis" / "localization_v3"
    directory.mkdir(parents=True)
    for name in overlay.FROZEN:
        (directory / f"{name}.py").write_text("# altered source\n")
    monkeypatch.setattr(overlay.v5_lean, "SOURCE", tmp_path)
    with pytest.raises(ValueError, match="frozen cavity sources"):
        overlay.frozen_hashes()


def test_completed_repeats_preserve_the_original_timeout_figures():
    cards = {c.id: c for c in screening_figures.charts([low.METHOD], evidence=overlay.REPORT)}
    primary, salted, repeats = (
        cards[f"{low.METHOD}-{g}"] for g in ("primary", "confirmation", "repeat")
    )
    assert primary.predictions["one"]["DS29-0082"]["result"]["status"] == "timed_out"
    assert salted.predictions["stock"]["DS26-0024"]["result"]["status"] == "timed_out"
    assert set(repeats.cases) == {"DS29-0082", "DS26-0024"}
    assert all(
        row["result"]["status"] == "ok"
        for series in repeats.predictions.values()
        for row in series.values()
    )
