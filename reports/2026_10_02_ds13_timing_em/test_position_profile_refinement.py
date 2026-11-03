import numpy as np
from position_profile_refinement import (
    SOUTH_PRIORITY,
    gradient_change,
    priority_labels,
    select_updated_best,
)


def _position(label, norm, radius=50.0, bearing=0.0, resolved=False):
    return {
        "label": label,
        "kind": "radial",
        "radius_m": radius,
        "bearing_deg": bearing,
        "ranking_resolved": resolved,
        "best": {
            "projected_nuisance_gradient_inf_norm": norm,
            "objective": 10.0,
        },
    }


def test_priority_places_south_cells_first_then_low_gradient_cells():
    positions = [
        _position("E-50m", 0.002, bearing=90.0),
        _position("S-500m", 0.05, radius=500.0, bearing=180.0),
        _position("S-50m", 0.008, bearing=180.0),
        _position("N-50m", 0.0015),
        _position("S-100m", 0.009, radius=100.0, bearing=180.0),
        _position("W-50m", 0.0005, bearing=270.0, resolved=True),
    ]
    labels = priority_labels(positions)
    assert labels[:3] == list(SOUTH_PRIORITY)
    assert labels[3:] == ["N-50m", "E-50m"]


def test_updated_best_retains_lowest_finite_even_if_nonconverged():
    original = {"objective": 10.0, "success": False}
    refinements = [
        {"objective": 9.0, "success": False},
        {"objective": 9.5, "success": True},
        {"objective": None, "success": False},
    ]
    source, best = select_updated_best(original, refinements)
    assert source == "refinement_1"
    assert best is refinements[0]


def test_gradient_change_reports_norm_ratio_and_vectors():
    before = {
        "projected_nuisance_gradient_inf_norm": 0.01,
        "free_position_gradient": np.array([1.0, 2.0]),
    }
    after = {
        "projected_nuisance_gradient_inf_norm": 0.002,
        "free_position_gradient": np.array([3.0, 4.0]),
    }
    result = gradient_change(before, after)
    assert result["projected_nuisance_gradient_ratio"] == 0.2
    np.testing.assert_array_equal(result["free_position_gradient_before"], [1.0, 2.0])
    np.testing.assert_array_equal(result["free_position_gradient_after"], [3.0, 4.0])
