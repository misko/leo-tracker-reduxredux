from math import hypot

import pytest

from reports.ALGO08.v3.ds30_centered_error import analyze
from reports.ALGO08.v3.ds30_position_moments import decompose, east_north_km
from tools.pipeline_eval.scoring import distance_km


@pytest.mark.parametrize(("reference", "endpoint", "direction"), (
    ((0, 0), (0, 10), (1, 0)),
    ((0, 0), (0, -10), (-1, 0)),
    ((40, 30), (45, 30), (0, 1)),
    ((40, 30), (35, 30), (0, -1)),
    ((0, 179.5), (0, -179.5), (1, 0)),
))
def test_chart_has_the_scoring_radius_and_local_direction(reference, endpoint, direction):
    result = east_north_km(reference, endpoint)
    distance = distance_km(reference, endpoint)
    assert hypot(*result) == pytest.approx(distance, rel=5e-12)
    assert result == pytest.approx(tuple(distance*axis for axis in direction), abs=5e-12)


def test_zero_and_antipodal_endpoints_have_explicit_semantics():
    assert east_north_km((53, 42), (53, 42)) == (0., 0.)
    with pytest.raises(ValueError, match="antipode"):
        east_north_km((0, 0), (0, 180))


def test_mean_displacement_does_not_change_centered_spread():
    values = [(1., 0.), (-1., 0.), (0., 1.), (0., -1.)]
    translated = [(e+3., n-4.) for e, n in values]
    original, shifted = decompose(values), decompose(translated)
    assert original["radial_mse_km2"] == original["centered_mse_km2"] == 1.
    assert shifted["radial_mse_km2"] == 26.
    assert shifted["squared_mean_offset_km2"] == 25.
    assert shifted["centered_mse_km2"] == 1.
    assert shifted["max_identity_residual_km2"] == 0.


def test_shared_scored_support_excludes_failed_and_unscored_fixes_only_from_scatter():
    def receipt(fix, *, outcome=None):
        return dict(outcome=outcome or ("complete" if fix else "withheld"),
                    arms={arm: dict(latlon=fix) for arm in ("c0", "fitted_c")})

    one = dict(installed=receipt((0., .1)), successor=receipt((0., .2)))
    candidate_only = dict(installed=receipt(None, outcome="solver_failed"), successor=receipt((0., .5)))
    captures = [("one", (0., 0.), one), ("unscored", None, one), ("candidate_only", (0., 0.), candidate_only)]
    result = analyze(captures)
    assert result["assigned"] == 3
    assert result["outcomes"]["installed"]["solver_failed"] == 1
    for arm in result["arms"].values():
        assert arm["shared"] == ["one"]
        assert arm["fixes"] == {"installed": 2, "successor": 3}
        assert arm["scored"] == {"installed": 1, "successor": 2}
        assert all(row["n"] == 1 and row["centered_mse_km2"] == 0 for row in arm["builds"].values())
