import itertools

import pytest
from compare_visit_identity import overlap


def test_equal_size_expectation_matches_exhaustive_subsets():
    a, b = ["a", "a", "b", "c", "d"], ["a", "b", "b", "e", "f"]
    values = [
        len(set(x) & set(y))
        for x in itertools.combinations(a, 4)
        for y in itertools.combinations(b, 4)
    ]
    assert overlap(a, b)["expected_shared_at_four"] == pytest.approx(sum(values) / len(values))


def test_repeated_words_count_once_and_disjoint_visits_have_zero_overlap():
    assert overlap(["a"] * 5, ["a"] * 8)["expected_shared_at_four"] == 1
    assert overlap(["a"] * 4, ["b"] * 4)["expected_shared_at_four"] == 0
    with pytest.raises(ValueError):
        overlap(["a"], ["a"] * 4)
