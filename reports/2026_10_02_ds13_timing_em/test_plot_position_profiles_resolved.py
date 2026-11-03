import numpy as np
import pytest

from plot_position_profiles_resolved import profile_plot_data, resolved_color_limit


def row(label, east, north, delta, success=True, resolved=True, radius=500):
    return {
        "label": label,
        "kind": "radial",
        "radius_m": radius,
        "fixed_position_km": [east, north],
        "delta_nll_from_truth": delta,
        "success": success,
        "ranking_resolved": resolved,
    }


def profile(radial):
    return {
        "session": "scan",
        "positions": [{
            "label": "truth",
            "kind": "reference",
            "radius_m": 0,
            "fixed_position_km": [10.0, 20.0],
            "delta_nll_from_truth": 0.0,
            "success": True,
            "ranking_resolved": True,
        }, *radial],
    }


def test_unresolved_points_are_excluded_from_quantitative_values():
    source = profile([
        row("resolved", 10.5, 20.0, -3.0),
        row("failed", 9.5, 20.0, -5000.0, success=False, resolved=False),
        row("unranked", 10.0, 20.5, 4000.0, success=True, resolved=False),
    ])
    data = profile_plot_data(source)
    assert [item["label"] for item in data["resolved_rows"]] == ["resolved"]
    assert [item["label"] for item in data["unresolved_rows"]] == ["failed", "unranked"]
    assert data["resolved_delta_nll"] == pytest.approx([-3.0])
    assert np.allclose(data["resolved_points"], [[0.5, 0.0]])
    assert np.allclose(data["unresolved_points"], [[-0.5, 0.0], [0.0, 0.5]])


def test_color_limit_ignores_unresolved_extremes_and_requires_resolved_point():
    mixed = profile([
        row("resolved", 10.5, 20.0, 4.0),
        row("unresolved", 9.5, 20.0, -10000.0, success=False, resolved=False),
    ])
    assert resolved_color_limit([mixed]) == pytest.approx(4.0)
    empty = profile([row("unresolved", 9.5, 20.0, -1.0, success=False, resolved=False)])
    with pytest.raises(ValueError, match="resolved radial"):
        resolved_color_limit([empty])


def test_truth_radius_zero_is_not_a_quantitative_profile_point():
    data = profile_plot_data(profile([row("resolved", 10.0, 20.05, 1.0, radius=50)]))
    assert len(data["resolved_rows"]) == 1
    assert np.allclose(data["resolved_points"], [[0.0, 0.05]])
