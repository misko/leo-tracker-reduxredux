from types import SimpleNamespace

import numpy as np
import profile_zoom
import pytest


def test_zoom_center_uses_only_coarse_objective():
    coarse = {
        "nodes": [
            {"node_index": 1, "position_km": [10, 20], "fit": {"objective": 1}},
            {"node_index": 0, "position_km": [0, 0], "fit": {"objective": 2}},
        ],
        "reference_position": [0, 0],
    }
    center, index = profile_zoom.zoom_center(coarse)
    np.testing.assert_array_equal(center, [10, 20])
    assert index == 1
    with pytest.raises(ValueError, match="finite coarse"):
        profile_zoom.zoom_center({"nodes": []})


def test_zoom_nodes_share_nuisance_seed_and_refine_by_objective(monkeypatch):
    calls = []
    initial = np.arange(8, dtype=float)
    data = SimpleNamespace(
        measured=np.zeros(4),
        times=np.arange(4),
        group=np.arange(4),
        rf=np.ones(4),
        receiver=np.zeros(4),
        channel=np.ones(4),
    )
    source = {
        "score_leader": {
            "satellite_indices": [0, 1],
            "parameters": initial,
            "objective": 100,
            "identity_masses": {},
            "success": True,
        },
        "anchors": [],
    }
    coarse = {"nodes": [{"node_index": 2, "position_km": [10, 20], "fit": {"objective": 5}}]}

    def refiner(data, parameters, satellites, support, likelihood, **options):
        fixed = options.get("fixed_position_km")
        calls.append((parameters.copy(), fixed))
        parameters = parameters.copy()
        if fixed is not None:
            parameters[:2] = fixed
        return {
            "parameters": parameters,
            "objective": float(np.sum((parameters[:2] - [10, 20]) ** 2)),
            "success": True,
        }

    monkeypatch.setattr(profile_zoom, "refine_gauss_newton", refiner)
    result = profile_zoom.fit_zoom(data, source, coarse)
    assert len(calls) == 28
    for parameters, fixed in calls[:25]:
        np.testing.assert_array_equal(parameters, initial)
        assert fixed is not None
    assert all(fixed is None for _, fixed in calls[25:])
    np.testing.assert_array_equal(result["selected"]["fit"]["parameters"][:2], [10, 20])
    assert result["local_search_resolved"]
    assert not result["bank_selection_reevaluated"]
