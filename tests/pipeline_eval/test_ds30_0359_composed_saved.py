import pytest

from reports.ALGO08.v3.ds30_0359_composed_score import grid_evidence


def test_grid_tolerance_never_substitutes_for_coordinate_or_minimum_parity():
    original = dict(complete=True, points=[dict(east_km=0., scores=dict(c0=0., fitted_c=1.)),
                                           dict(east_km=1., scores=dict(c0=1., fitted_c=0.))])
    candidate = dict(original, points=[dict(original["points"][0], scores=dict(c0=1e-12, fitted_c=1.)),
                                      original["points"][1]])
    assert all(item["qualified"] for item in grid_evidence(original, candidate).values())
    changed = dict(candidate, points=[dict(candidate["points"][0], east_km=2.), candidate["points"][1]])
    with pytest.raises(ValueError, match="coordinates"):
        grid_evidence(original, changed)
    close = dict(original, points=[dict(point, scores=dict(c0=0., fitted_c=0.)) for point in original["points"]])
    alternate = dict(close, points=[dict(close["points"][0], scores=dict(c0=1e-12, fitted_c=0.)), close["points"][1]])
    assert not grid_evidence(close, alternate)["c0"]["qualified"]
