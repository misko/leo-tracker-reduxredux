import math
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))

from lean_named_parity import compare_owners, grid_comparison, residual_roles


def test_owner_delta_separates_order_roles_and_norad_changes():
    left = [["a", 1, "conditional"], ["b", 2, "conditional"], ["c", 3, "predictive"]]
    right = [["b", 2, "predictive"], ["a", 4, "conditional"], ["d", 3, "predictive"]]
    delta = compare_owners(left, right)
    assert not delta["ordered_equal"]
    for key in ("lost", "added", "changed_norad", "changed_role"):
        assert delta[key] == 1
    reordered = compare_owners(left, left[::-1])
    assert reordered["shared"] == 3 and not reordered["ordered_equal"]


def test_predictive_rms_uses_weighted_role_squares_and_rejects_unrelated_role():
    combined = math.sqrt((3*4**2 + 2*12**2)/5)
    assert residual_roles(4, combined, {"conditional": 3, "predictive": 2}) == pytest.approx(12)
    with pytest.raises(ValueError):
        residual_roles(4, combined, {"conditional": 3, "predictive": 2, "other": 1})


def test_grid_comparison_preserves_order_and_counts_equal_coordinate_failures():
    rows = [dict(east_km=i, north_km=0, latlon=[i, i], scores={"c0": i, "fitted_c": i}) for i in range(2)]
    compared = [rows[1] | {"scores": {"c0": 1.25, "fitted_c": None}}, rows[0]]
    delta = grid_comparison({"points": rows}, {"points": compared})
    assert delta["shared"] == 2 and not delta["same_order"]
    assert delta["arms"]["c0"]["maximum_absolute_delta"] == 0.25
    assert delta["arms"]["fitted_c"]["unmatched_failures"] == 1
