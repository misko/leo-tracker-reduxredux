"""Lower RMS cannot outrank whole-track residual evidence or recruit lines."""

from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.research.track_evidence_objective import (
    feasible_track_candidates,
    score_track_evidence,
)


def setup(residuals, costs, *, shared=False):
    residuals = np.asarray(residuals)
    fragments, candidates, n = residuals.shape
    components = 1 if shared else fragments
    stats = dict(
        fragments=[dict(times=np.arange(n, dtype=float)) for _ in range(fragments)],
        fragment_active=np.ones(fragments, bool),
        ci=np.zeros(fragments, int) if shared else np.arange(fragments),
        starts=np.array([0]) if shared else np.arange(fragments),
        n=np.full(fragments, n),
        count=np.full(components, n * fragments if shared else n),
        component_visible=np.ones((components, candidates), bool),
        hm=np.zeros((fragments, candidates)),
        hh=np.zeros((fragments, candidates)),
        mean=np.zeros((fragments, candidates)),
    )
    terms = SimpleNamespace(
        score=np.asarray(costs),
        residual_mse=np.full((components, candidates), 150**2),
        bias_hz=np.zeros((components, candidates)),
    )

    def provider(fi, indexes):
        return residuals[fi, indexes]

    return stats, terms, provider


def score(stats, terms, provider, phases=None):
    satellites = terms.score.shape[1]
    return score_track_evidence(
        stats,
        terms,
        np.zeros(8),
        np.zeros(satellites) if phases is None else phases,
        np.ones(satellites),
        provider,
    )


def test_low_energy_structured_residual_cannot_earn_calibration_evidence():
    white = np.random.default_rng(1).normal(0, 120, 40)
    structured = np.linspace(-150, 150, 40)
    good = setup(white[None, None, :], [[20000.0]])
    bad = setup(structured[None, None, :], [[8000.0]])
    good_score, bad_score = score(*good), score(*bad)
    assert good_score["compatible_curved_points"] == 40
    assert bad_score["compatible_curved_points"] == 0
    assert good_score["score"] < bad_score["score"]


def test_candidate_is_selected_after_every_residual_gate():
    r = np.stack([np.linspace(-150, 150, 40), np.random.default_rng(1).normal(0, 120, 40)])
    result = score(*setup(r[None, :, :], [[8000, 20000]]))
    assert result["selected_candidate_indexes"].tolist() == [1]
    assert result["feasible_candidate_counts"].tolist() == [1]


def test_noncurved_fragment_cannot_rank_hardware_states():
    args = setup(np.zeros((1, 1, 20)), [[0]])
    args[0]["fragment_active"][0] = False
    with pytest.raises(ValueError, match="only measured-curved"):
        score(*args)


def test_linear_fragment_can_associate_after_calibration_without_ranking_states():
    stats, terms, provider = setup(np.zeros((1, 1, 20)), [[0]])
    stats["fragment_active"][0] = False
    assert feasible_track_candidates(stats, terms, provider).tolist() == [[True]]
    with pytest.raises(ValueError, match="only measured-curved"):
        score(stats, terms, provider)


def test_member_means_cannot_cancel_in_a_shared_component():
    r = np.array([np.full((1, 20), 400.0), np.full((1, 20), -400.0)])
    result = score(*setup(r, [[10000]], shared=True))
    assert result["compatible_curved_points"] == 0
    assert result["component_supported"].tolist() == [False]


def test_phase_prior_charged_once_and_no_information_from_rejected_components():
    args = setup(np.zeros((1, 1, 20)), [[0]])
    zero, shifted = score(*args), score(*args, phases=np.ones(1))
    assert shifted["score"] - zero["score"] == pytest.approx(150**2)
    args[1].bias_hz[0, 0] = 4000
    args[0]["hh"][0, 0] = 1e8
    rejected = score(*args)
    assert rejected["parts"]["conditional_phase_complexity"] == 0
    assert rejected["compatible_curved_points"] == 0


def test_bad_nominee_pays_clutter_without_vetoing_three_coherent_curved_components():
    white = np.random.default_rng(1).normal(0, 120, 40)
    structured = np.linspace(-150, 150, 40)
    old = setup(np.array([[structured], [structured], [structured], [white]]), [[8000]] * 4)
    new = setup(np.array([[white], [white], [white], [structured]]), [[20000]] * 4)
    before = score(*old)
    after = score(*new, phases=np.array([-2.7]))
    assert after["component_supported"].tolist() == [True, True, True, False]
    assert after["total_calibration_points"] == 160
    assert after["compatible_curved_points"] == 120
    assert after["parts"]["frequency_or_clutter"] == pytest.approx(3 * 40 * 20000 + 40 * 900**2)
    assert after["score"] < before["score"]
    new[0]["hh"][3, 0] = 1e12
    assert score(*new, phases=np.array([-2.7]))["score"] == pytest.approx(after["score"])
