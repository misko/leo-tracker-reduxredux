import pytest

from reports.ALGO08.v3.three_replay_coverage import substitute


def field(case, error):
    return dict(case=case, wall_units=9, c0_fix=error is not None, fitted_c_fix=error is not None,
                c0_error_km=error, fitted_c_error_km=error)


def test_replay_substitution_preserves_clocks_withholds_and_other_recordings():
    original = [(field("a", 1.2), field("a", 1.1)), (field("b", .3), field("b", None))]
    changes = {"a":{"c0":(1100., 800.), "fitted_c":(1100., 1300.)}}
    result = substitute(original, changes)
    assert result == [(original[0][0], field("a", 1.1) | dict(c0_error_km=.8, fitted_c_error_km=1.3)), original[1]]
    assert original[0][1]["c0_error_km"] == 1.1
    with pytest.raises(ValueError):
        substitute(original, {"b":changes["a"]})
    with pytest.raises(ValueError):
        substitute(original, {"a":dict(c0=(1., 800.), fitted_c=(1100., 1300.))})
    with pytest.raises(ValueError):
        substitute(original, {"absent":changes["a"]})
