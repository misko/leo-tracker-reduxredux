from types import SimpleNamespace

import numpy as np
import pytest

from leo.application import channel_group_discovery as module


class Port:
    def __init__(self):
        self.rows = {}

    def get(self, key):
        return self.rows.get(key)

    def put(self, key, value):
        assert key not in self.rows
        self.rows[key] = value


@pytest.mark.parametrize("early_clock", [False, True])
@pytest.mark.parametrize("priority_view", ["all", "low", "high"])
def test_discovery_reuses_training_receipts_and_matches_candidate_banks(
    monkeypatch, early_clock, priority_view
):
    views = {
        view: SimpleNamespace(
            observations=SimpleNamespace(channel=np.array(channels), name=view),
            bootstrap_tracks=((0, 1, 2),),
        )
        for view, channels in (("low", [1, 2]), ("high", [7, 8]), ("all", [1, 7]))
    }
    calls, selected_banks = [], []

    def bootstrap(obs, bank, prior, point, tracks, **kwargs):
        calls.append(obs.name)
        return SimpleNamespace(
            satellite_indices={"low": (0, 1), "high": (1, 2), "all": (2, 3)}[obs.name]
        )

    def objective(obs, subset, *_):
        selected_banks.append((obs.name, subset))
        return SimpleNamespace(observations=obs)

    def search(evaluate, **kwargs):
        for point in ((0.0, 0.0), (25.0, 0.0), (0.0, 25.0)):
            assert evaluate(*point) == {"low": 1.0, "high": 2.0, "all": 3.0}[priority_view]
        return module.hierarchical_search_original

    monkeypatch.setattr(module, "bootstrap_position", bootstrap)
    monkeypatch.setattr(module, "Hard60Objective", objective)
    clock_calls = []

    def clock(base, nodes, knots, scale):
        np.testing.assert_array_equal(nodes, [0.0, 30.0, 60.0])
        np.testing.assert_array_equal(knots, np.zeros((2, 3)))
        assert scale == 4
        clock_calls.append(base.observations.name)
        return base

    monkeypatch.setattr(module, "JointClockObjective", clock)
    monkeypatch.setattr(module, "GroupCalibrationObjective", lambda base, _: base)
    monkeypatch.setattr(
        module,
        "shared_bootstrap_seed",
        lambda *_: dict(vector=[0.0], nuisance=[], projection=dict(rms_hz=0.0)),
    )
    monkeypatch.setattr(
        module,
        "fit_group_calibration",
        lambda model, *_, **__: dict(
            objective={"low": 1.0, "high": 2.0, "all": 3.0}[model.observations.name], converged=True
        ),
    )
    from leo.analysis.regional_position_search import SpatialSearch

    monkeypatch.setattr(
        module, "hierarchical_search_original", SpatialSearch((), 0, "test"), raising=False
    )
    monkeypatch.setattr(module, "hierarchical_search", search)
    bank = SimpleNamespace(numbers=np.arange(1001, 1005), select=lambda indices: tuple(indices))
    port = Port()
    options = dict(clock_nodes=np.array([0.0, 30.0, 60.0])) if early_clock else {}
    options["priority_view"] = priority_view
    result = module.discover_channel_groups(
        views, bank, SimpleNamespace(radius_km=250.0), port, **options
    )
    assert result["available"] and result["points"] == 3
    assert len(calls) == 9
    assert all(subset == (0, 1, 2, 3) for _, subset in selected_banks)
    assert len(clock_calls) == (9 if early_clock else 0)
    module.discover_channel_groups(views, bank, SimpleNamespace(radius_km=250.0), port, **options)
    assert len(calls) == 9


def test_discovery_refuses_missing_training_all_and_unbounded_slice():
    with pytest.raises(ValueError):
        module.discover_channel_groups({}, None, None, None)
    with pytest.raises(ValueError):
        module.discover_channel_groups({"all": None}, None, None, None, maximum_seconds=1800.0)
