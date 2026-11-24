import pytest

from reports.ALGO08.v3.ds30_field_error_influence import compare_centers


def test_offer_distance_is_scored_at_original_center_and_nonfix_stays_assigned():
    def row(case, error):
        return dict(case=case, c0_error_km=error, fitted_c_error_km=error)

    offer = dict(center=[0, .1], screen_center=[0, .2], width_km=25)
    cases = {"a": {"reference": [0, 0]}, "b": {"reference": [0, 0]}}
    pairs = [(row("a", None), row("a", 1)), (row("b", 12), row("b", 0))]
    prior = compare_centers(pairs, cases, offer)
    assert prior["center_error_km"] == pytest.approx(11.119508, rel=1e-6)
    assert prior["screen_center_distance_km"] == pytest.approx(2*prior["center_error_km"])
    assert prior["fixes"]["c0"] == {
        "installed": {"assigned": 2, "scored": 1, "closer_than_center": 0},
        "successor": {"assigned": 2, "scored": 2, "closer_than_center": 2}}
    cases["b"]["reference"] = [1, 0]
    with pytest.raises(ValueError, match="one independently surveyed"):
        compare_centers(pairs, cases, offer)
