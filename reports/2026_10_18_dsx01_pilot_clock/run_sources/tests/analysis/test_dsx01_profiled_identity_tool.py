import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from test_dsx01_rf_clock_tool import problem_inputs


@pytest.fixture
def tool():
    path = str(Path(__file__).resolve().parents[2] / "tools")
    sys.path.insert(0, path)
    try:
        yield importlib.import_module("iterate_dsx01_profiled_identity")
    finally:
        sys.path.remove(path)


def test_incompatible_component_phases_do_not_get_averaged_into_a_fake_shared_phase(tool):
    phase, support, count = tool.coherent_phase([-2, -1.95, 7], [0.05, 0.05, 0.05], [1, 1, 1])
    assert -2 <= phase <= -1.95
    assert support == 2 and count == 2


def test_invalid_proposal_support_is_explicit(tool):
    with pytest.raises(ValueError):
        tool.coherent_phase([1], [0], [1])
    with pytest.raises(ValueError):
        tool.coherent_phase([1], [1], [0])


def test_exploration_cannot_replace_a_better_incumbent(tool, monkeypatch, tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    (source / "case").mkdir(parents=True)
    (output / "case" / "shared_phase").mkdir(parents=True)
    (source / "case" / "endpoints.json").write_text(
        json.dumps({"c0/shared_phase": dict(score=1), "fitted_c/shared_phase": dict(score=2)})
    )
    monkeypatch.setattr(tool, "SOURCE", source)
    monkeypatch.setattr(tool, "OUTPUT", output)
    records = [dict(iteration=0, fits={"c0": dict(score=3), "fitted_c": dict(score=4)})]
    result = tool.select_endpoints("case", "shared_phase", records)
    assert result["c0"]["score"] == 1 and result["fitted_c"]["score"] == 2
    assert all(v["selected_from"] == "inherited" for v in result.values())


def test_wide_radio_state_is_not_reset_by_legacy_update(tool, monkeypatch):
    scan, seed = problem_inputs()
    scan.geometry, scan.groups = {}, []
    seed["state"]["beta"][4] = 1500.0
    stats = dict(
        n=np.ones(1),
        hh=np.ones((1, 1)),
        hm=np.zeros((1, 1)),
        count=np.array([31]),
        active=np.ones(1, bool),
        fragment_active=np.ones(1, bool),
    )
    monkeypatch.setattr(tool, "phase_linear_frequency", lambda *args: (None, None, None))
    monkeypatch.setattr(tool.matching, "statistics", lambda *args: stats)
    monkeypatch.setattr(tool, "augment_phase_statistics", lambda stats, *args: stats)
    monkeypatch.setattr(
        tool, "proposal_phases", lambda *args, **kwargs: (np.array([[0.2]]), np.zeros((1, 1)))
    )
    monkeypatch.setattr(tool, "native_point", lambda scan, anchor: anchor)
    monkeypatch.setattr(tool, "nomination_rows", lambda scan, rows, nominations: rows)
    scan.association = lambda *args: (0.0, seed["rows"], {}, None)

    def unexpected_update(*args):
        raise AssertionError("legacy bounded update must not replace calibrated wide radio state")

    scan.update = unexpected_update
    result, _ = tool.explore(scan, seed["state"], (0, 0), "shared_phase", compact_update=False)
    assert result["state"]["beta"][4] == 1500
    assert result["state"]["phases"][0] == pytest.approx(0.2)
