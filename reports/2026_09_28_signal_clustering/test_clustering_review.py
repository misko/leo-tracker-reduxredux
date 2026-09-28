import numpy as np
import pytest
from clustering_review import balanced_resampling, profile_matrix


@pytest.mark.parametrize("metric", ["js", "hellinger", "jaccard"])
def test_profile_distances_match_and_disjoint(metric):
    matrix = profile_matrix([["a", "a"], ["a"], ["b"]], metric)
    assert matrix[0, 1] == 0
    assert matrix[0, 2] == pytest.approx(1)
    np.testing.assert_array_equal(matrix, matrix.T)


def test_presence_and_frequency_answer_different_questions():
    sequences = [["a"] * 9 + ["b"], ["a"] + ["b"] * 9]
    assert profile_matrix(sequences, "jaccard")[0, 1] == 0
    assert profile_matrix(sequences, "js")[0, 1] > 0.7
    with pytest.raises(ValueError):
        profile_matrix([[], ["a"]])


def test_subsampling_is_reproducible_and_preserves_separated_groups():
    sequences = [["a"] * 12, ["a"] * 10, ["b"] * 11, ["b"] * 13]
    draws, consensus = balanced_resampling(sequences, repetitions=5, cuts=(2,))
    np.testing.assert_array_equal(
        draws, balanced_resampling(sequences, repetitions=5, cuts=(2,))[0]
    )
    assert consensus[2][0, 1] == 1
    assert consensus[2][0, 2] == 0
    np.testing.assert_array_equal(np.diag(consensus[2]), 1)
    with pytest.raises(ValueError):
        balanced_resampling(sequences, size=14)


def test_full_size_subsampling_does_not_change_distance():
    sequences = [["a", "a", "b"], ["a", "b", "b"], ["c", "c", "c"]]
    draws, _ = balanced_resampling(sequences, size=3, repetitions=3, cuts=(2,))
    for draw in draws:
        np.testing.assert_allclose(draw, profile_matrix(sequences))
