import held_shrink_0274_score as score
import pytest


def test_ordinary_parity_rejects_a_missing_owner_or_changed_grid():
    expected = {"owners": [["a", 1, "anchor"]], "grid": [0., 1.]}
    score.require_parity(dict(expected), expected)
    with pytest.raises(ValueError, match="raw incumbent"):
        score.require_parity(dict(expected, owners=[]), expected)
    with pytest.raises(ValueError, match="raw incumbent"):
        score.require_parity(dict(expected, grid=[0., 1.0001]), expected)
