from math import nextafter
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from field_initializer_identifiability import rank_rows, scout_choices, score_links


def test_exact_scores_distinguish_a_scalar_link_from_an_assignment():
    assert score_links([3., nextafter(1., 2.), 1.], [1., 2., 3.]) == [[3], [], [1]]
    assert score_links([1., 2., 3.], [1., 1., 2.]) == [[1, 2], [3], []]


def test_incomplete_comparison_fails_closed():
    with pytest.raises(ValueError, match="complete"):
        score_links([1., 2., float("inf")], [1., 2., 3.])


def test_branch_signatures_keep_original_signed_aliases():
    assert rank_rows([["a", 0, 10, -1], ["b", 1, 11, 0]]) == {
        "a": [0, 10, -1], "b": [1, 11, 0]}
    with pytest.raises(ValueError, match="Duplicate"):
        rank_rows([["a", 0, 10, -1], ["a", 0, 10, -1]])


def test_radio_mean_and_minimax_choices_distinguish_archived_candidate_indices():
    trace = dict(requested=[dict(index=1, per_radio=[6., 7.]), dict(index=5, per_radio=[2., 9.])],
                 picked=1, paid_centres=2)
    read = scout_choices(trace)
    assert (read["minimax"], read["mean"], read["per_radio"]) == (1, 5, [5, 1])
    assert read["scout_to_signature_link_available"] is False
