from types import SimpleNamespace

import numpy as np
import pytest
from audit_core import audit
from pair_score import zero_score

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import ALIAS_HZ


def fixture():
    rows = [
        dict(
            window_id=str(i),
            receiver=0,
            channel=1,
            actual_rf_hz=11e9,
            edge="lower",
            support_start_ns=i * 100,
            support_center_ns=i * 100 + 5,
            support_end_ns=i * 100 + 10,
            acquisition_id=str(i),
        )
        for i in range(5)
    ]
    support = dict(rows=rows, unavailable_reasons={})
    terms = SimpleNamespace(
        nll=3.0,
        responsibilities=np.ones((5, 1)),
        residual_hz=np.asarray([[125], [125], [125], [-125], [0]]),
    )
    calls = []

    def evaluate(vector, clock):
        calls.append((vector.copy(), clock.copy()))
        return 3.0, None, None, terms

    model = SimpleNamespace(
        observations=SimpleNamespace(window_ids=tuple(str(i) for i in range(5))),
        score=SimpleNamespace(sigma_hz=125),
        evaluate_joint=evaluate,
    )
    archive = dict(
        stages=dict(
            B7={
                arm: dict(vector=[i], clock_coefficients=[i], objective=3.0)
                for i, arm in enumerate(("fitted-c", "zero-c"))
            }
        )
    )
    return model, archive, support, calls


def test_both_saved_endpoints_no_fit_complete_accounting_and_fixed_blocks():
    model, archive, support, calls = fixture()
    result = audit(model, archive, support)
    assert len(calls) == 2 and calls[0][0][0] == 0 and calls[1][0][0] == 1
    assert result["optimizer_calls"] == 0 and not result["position_evaluation"]
    assert result["observations"] == 5 and len(result["pairing"]["unpaired"]) == 1
    for arm in result["arms"].values():
        assert arm["score_sum"] == 0
        assert [r["alternating_block"] for r in arm["pair_details"]] == [0, 1]
        assert [r["score_sum"] for r in arm["groups"][0]["alternating_blocks"]] == [1, -1]


def test_observation_order_and_archive_parity_are_required():
    model, archive, support, calls = fixture()
    support["rows"].reverse()
    with pytest.raises(ValueError, match="observation order"):
        audit(model, archive, support)
    assert not calls
    support["rows"].reverse()
    archive["stages"]["B7"]["fitted-c"]["objective"] = 4
    with pytest.raises(ValueError, match="objective mismatch"):
        audit(model, archive, support)


def test_narrow_production_score_matches_wrapped_moments_at_alias_seams():
    score = SimpleNamespace(sigma_hz=125, detection_budget=1.6, clutter_rate=0.5)
    prediction = np.array([[0, ALIAS_HZ / 2 - 50, -ALIAS_HZ / 2 + 70]] * 4)
    measured = np.array([30, 60, ALIAS_HZ / 2 - 1, -ALIAS_HZ / 2 + 1])
    visible = np.ones(prediction.shape, bool)
    terms = likelihood(measured, prediction, visible, score)
    z = (terms.residual_hz[..., None] + np.array([-1, 0, 1]) * ALIAS_HZ) / 125
    phi = np.exp(-0.5 * z**2) / (125 * np.sqrt(2 * np.pi))
    q = 1.6 / prediction.shape[1]
    coefficient = q / (1 - q)
    density = coefficient * phi.sum(axis=2)
    total = 0.5 / ALIAS_HZ + density.sum(axis=1)
    # Weighted moments avoid 0/0 at components whose entire density underflows.
    moment = coefficient * (phi * z).sum(axis=2) / total[:, None]
    expected = np.sum(moment[[0, 2]] * moment[[1, 3]], axis=1)
    actual = zero_score(terms.responsibilities, terms.residual_hz / 125, [(0, 1), (2, 3)])
    np.testing.assert_allclose(actual["pair_scores"], expected, rtol=1e-14, atol=1e-14)
