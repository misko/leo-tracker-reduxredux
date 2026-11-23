import importlib
from pathlib import Path

import pytest


def test_budget_handles_both_gates_and_impossible_reader(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    model = importlib.import_module("full_short_live_budget")
    row = {"stages": [5, 5, 0], "compressed_MB": 20}
    assert model.maximum_fraction([row], 2, 0) is None
    assert model.maximum_fraction([row], 20, 1) == pytest.approx(.6)
    data = model.evaluate(model.HERE / "live-inference-profile-summary.json")
    assert data["recordings"] == 55 and data["unchanged_uninstrumented"] == 3
    for result in data["estimates"]:
        assert result["median_and_summed"][0] > .5 and result["median_and_summed"][1] > .5
