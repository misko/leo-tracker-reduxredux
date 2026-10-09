import importlib.util
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.hard60_score import likelihood
from leo.analysis.regional_position_score import zero_sum_basis
from leo.contracts.regional_position import POSITION_SCORES

SPEC = importlib.util.spec_from_file_location(
    "fixed_bank114", Path(__file__).with_name("fixed_bank.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SCORE = replace(POSITION_SCORES["V16"], relative_sigma_s=2.0)


@pytest.mark.parametrize("batch_size", [1, 2, 7, 64])
def test_dense_streamed_varying_visibility(batch_size):
    rng = np.random.default_rng(114)
    measured = rng.normal(0, 100, 53)
    prediction = rng.normal(0, 300, (53, 19))
    visible = rng.random(prediction.shape) > 0.4
    visible[0] = False
    batches = (
        (prediction[:, i : i + batch_size], visible[:, i : i + batch_size])
        for i in range(0, 19, batch_size)
    )
    result = MODULE.streamed_score(
        measured, batches, candidate_count=19, score=SCORE, penalty=12.375
    )
    oracle = likelihood(measured, prediction, visible, SCORE)
    assert result["data_nll"] == pytest.approx(oracle.nll, rel=0, abs=1e-10)
    assert result["objective"] == pytest.approx(oracle.nll + 12.375, rel=0, abs=1e-10)
    np.testing.assert_array_equal(result["visible_count"], visible.sum(axis=1))


def test_invisible_additions_equal_denominator_only_but_change_native():
    measured = np.array([0.0, 100.0, 1000.0])
    prediction = np.array([[0.0, 200.0], [20.0, 250.0], [0.0, 400.0]])
    visible = np.ones_like(prediction, dtype=bool)
    normalized = MODULE.streamed_score(
        measured, [(prediction, visible)], candidate_count=5, score=SCORE, penalty=0
    )
    expanded = np.column_stack([prediction, np.full((3, 3), 12000.0)])
    mask = np.column_stack([visible, np.zeros((3, 3), dtype=bool)])
    assert normalized["data_nll"] == pytest.approx(likelihood(measured, expanded, mask, SCORE).nll)
    assert abs(normalized["data_nll"] - likelihood(measured, prediction, visible, SCORE).nll) > 0.01


def test_visible_off_frequency_changes_detection_factor():
    y = np.zeros(3)
    p = np.column_stack([y, y + 300, y + 50000])
    invisible = np.ones_like(p, dtype=bool)
    invisible[:, -1] = False
    visible = np.ones_like(p, dtype=bool)
    a = MODULE.streamed_score(y, [(p, invisible)], candidate_count=3, score=SCORE, penalty=0)
    b = MODULE.streamed_score(y, [(p, visible)], candidate_count=3, score=SCORE, penalty=0)
    assert b["data_nll"] == pytest.approx(likelihood(y, p, visible, SCORE).nll)
    assert abs(a["data_nll"] - b["data_nll"]) > 0.01


def test_zero_sum_transport_preserves_predictions_and_penalty():
    old = [10, 20, 30]
    new = [40, 30, 10, 50, 20]
    relative = np.array([-3.0, 1.0, 2.0])
    result = MODULE.transport_timing(old, new, 4.0, relative)
    np.testing.assert_allclose(result["physical_shifts_s"][[2, 4, 1]], 4 + relative, atol=1e-12)
    np.testing.assert_array_equal(result["relative_s"][[0, 3]], 0)
    np.testing.assert_allclose(
        zero_sum_basis(5) @ result["relative_coefficients"], result["relative_s"], atol=1e-12
    )
    before = 0.5 * (4 / SCORE.common_sigma_s) ** 2 + 0.5 * np.sum(
        (relative / SCORE.relative_sigma_s) ** 2
    )
    after = 0.5 * (result["common_s"] / SCORE.common_sigma_s) ** 2 + 0.5 * np.sum(
        (result["relative_s"] / SCORE.relative_sigma_s) ** 2
    )
    assert after == before


@pytest.mark.parametrize(
    "common,relative,new",
    [
        (11, [-1, 1], [1, 2, 3]),
        (0, [-21, 21], [1, 2, 3]),
        (0, [1, 1], [1, 2, 3]),
        (0, [-1, 1], [1, 3]),
    ],
)
def test_impossible_transport_rejected(common, relative, new):
    with pytest.raises(ValueError):
        MODULE.transport_timing([1, 2], new, common, relative)


def test_invalid_batch_and_count_rejected():
    with pytest.raises(ValueError):
        MODULE.streamed_score(
            [0],
            [(np.zeros((1, 4)), np.ones((1, 4), bool))],
            candidate_count=3,
            score=SCORE,
            penalty=0,
        )
    with pytest.raises(ValueError):
        MODULE.streamed_score(
            [0],
            [(np.array([[np.nan, 0]]), np.ones((1, 2), bool))],
            candidate_count=2,
            score=SCORE,
            penalty=0,
        )
