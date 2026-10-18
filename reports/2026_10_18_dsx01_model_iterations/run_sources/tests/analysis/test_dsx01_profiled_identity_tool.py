import importlib
import json
import sys
from pathlib import Path

import pytest


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
