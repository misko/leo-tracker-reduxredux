import json

import numpy as np
import pytest
import timing10_comparison as module


def coherent():
    return {"fit": {"rx_initial": [1., 2., 3000., -50., 4000., 50., 2., -3.],
                    "rough": {"position_km": [1., 2.], "success": True}}}


def test_initializer_preserves_rx_and_zeros_only_timing():
    source = coherent()
    result = module.initial_parameters(source, 2)
    np.testing.assert_array_equal(result, [1., 2., 3000., -50., 4000., 50., 0., 0.])
    assert source["fit"]["rx_initial"][-2:] == [2., -3.]


@pytest.mark.parametrize("index,value", [(0, 201), (3, -50.01), (5, 50.01), (4, np.nan)])
def test_reject_infeasible_initializer(index, value):
    source = coherent()
    source["fit"]["rx_initial"][index] = value
    with pytest.raises(ValueError):
        module.initial_parameters(source, 2)


def test_rough_success_required():
    source = coherent()
    source["fit"]["rough"]["success"] = False
    with pytest.raises(ValueError):
        module.initial_parameters(source, 2)


def test_explicit_q01_parent_only():
    assert module.parent_path("DS10-Q01").parent.parent.name.endswith("legacy-retry-v1")
    assert module.parent_path("DS11-Q01").parent.parent.name == "finite-set-grouped-cohort-v1"


def test_full_cohort_counts_required(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "ROOT", tmp_path)
    selection = {"datasets": {dataset: {"units": [
        {"size": size, "unit_id": f"{dataset}-{size}-{index}"}
        for size, count in ((1, 16), (2, 8), (4, 4)) for index in range(count)
    ]} for dataset in ("DS10", "DS11")}}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection))
    assert len(module.units()) == 56
    selection["datasets"]["DS11"]["units"].pop()
    path.write_text(json.dumps(selection))
    with pytest.raises(ValueError, match="56-unit"):
        module.units()
