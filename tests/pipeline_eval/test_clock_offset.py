"""Verify the track offset integral and truly prefix-owned forecast."""

import numpy as np
import pytest

from tools.pipeline_eval.variants import clock_offset as model
from tools.pipeline_eval.variants import robust_em as lean


@pytest.mark.parametrize("ou", [False, True])
@pytest.mark.parametrize("sigma", [0.0, 1000.0])
def test_conditional_innovation_and_determinant_against_schur_complement(ou, sigma):
    t = np.array([0.0, 0.2, 2.0, 6.0, 7.0, 12.0])
    residual = np.array([100, -40, 600, 450, -700, 250])
    prefix = 3
    covariance = np.eye(len(t)) * lean.WHITE_HZ**2 + sigma**2
    if ou:
        covariance += lean.CORRELATED_HZ**2 * np.exp(
            -abs(t[:, None] - t) / lean.CORRELATION_S
        )
    cross = covariance[prefix:, :prefix]
    conditioned = residual[prefix:] - cross @ np.linalg.solve(
        covariance[:prefix, :prefix], residual[:prefix]
    )
    cov = covariance[prefix:, prefix:] - cross @ np.linalg.solve(
        covariance[:prefix, :prefix], cross.T
    )
    expected = conditioned @ np.linalg.solve(cov, conditioned) + np.linalg.slogdet(cov)[1]
    expected += len(conditioned) * np.log(2 * np.pi)
    square, deviance, count = model.conditional(t, residual, prefix, sigma, ou)
    assert count == len(conditioned)
    assert square == pytest.approx(conditioned @ conditioned)
    assert deviance == pytest.approx(expected)


def test_scaled_rank_one_whitening_preserves_the_marginal_penalty():
    size, sigma = 7, 1000.0
    diagonal = model.Diagonal()
    wrapped = model.Whitening(model.offset.ConstantPrior(diagonal, size, sigma))
    y = np.arange(0, 700, 100)
    actual = (0.7 * wrapped) @ y
    covariance = np.eye(size) * lean.WHITE_HZ**2 + sigma**2
    assert actual @ actual == pytest.approx(0.7**2 * (y @ np.linalg.solve(covariance, y)))
    design = np.column_stack((y, np.ones(size)))
    np.testing.assert_allclose(wrapped @ design, np.column_stack([wrapped @ a for a in design.T]))


def test_held_nomination_sees_only_prefix_and_reuses_alias(monkeypatch):
    t = np.arange(9.0)
    y = np.r_[np.zeros(6), np.ones(3) * 1700]
    tr = lean.Track(t, y, 11.5e9, 0, True, t / 100, np.eye(len(t)))
    full = lean.Arc(
        tr, np.array([1]), y[None], np.zeros((1, 9, 2)), np.ones((1, 9)),
        np.zeros(1), np.zeros(1),
    )
    seen = []

    def shortlist(tile, track):
        assert len(track.t) == 6
        assert not np.any(track.hz)
        seen.append(track)
        return lean.Arc(
            track, np.array([7]), track.hz[None], np.zeros((1, 6, 2)), np.ones((1, 6)),
            np.zeros(1), np.zeros(1),
        )

    def assign(arcs, state, *, update_phase):
        assert update_phase is False
        return [lean.Assignment(arcs[0], 0, -2, 0.0, 1.0)]

    monkeypatch.setattr(model.lean, "shortlist", shortlist)
    monkeypatch.setattr(model.lean, "assign", assign)
    (chosen,) = model._held_rows([full], None, None)
    assert len(seen) == 1
    assert chosen.prefix == 6
    assert chosen.assignment.orbit == 7
    assert chosen.assignment.alias == -2
    np.testing.assert_array_equal(chosen.assignment.arc.track.hz, y)


def test_dedicated_roof_figures_reuse_the_matched_overlay_seal():
    from tools.pipeline_eval.qualification import clock_offset_results as results

    curves = [
        dict(key=key, value=method, label=method, file=results.ALL, where={"cohort": "roof"})
        for key, method in zip(
            ("one", "stock", "one_native_factors", "all_visits"), results.METHODS, strict=True,
        )
    ]
    overlay = dict(
        id=results.FULL_ROOF_OVERLAY, seal="all_roof-figure-lock.json",
        source_lock={"file": "plan.json", "digest_key": "plan_sha256"}, series=curves, scope="roof",
    )
    omitted = {"id": "native_clock_offset-full-omitted"}
    expanded = results.with_model_roofs([overlay, omitted])
    assert expanded[:2] == [overlay, omitted]
    assert results.with_model_roofs(expanded) == expanded
    assert tuple(spec["id"] for spec in expanded[2:]) == results.MODEL_ROOF_IDS
    for spec, method in zip(expanded[2:], results.METHODS, strict=True):
        assert spec["method"] == method
        assert spec["cases"] == "roof135"
        assert spec["seal"] == overlay["seal"]
        assert spec["source_lock"] == overlay["source_lock"]
        assert spec["series"] == [
            dict(key="one", value=method, label=method, file=results.ALL, where={"cohort": "roof"}),
        ]
